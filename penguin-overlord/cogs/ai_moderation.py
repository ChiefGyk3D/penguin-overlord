# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""AI Moderation Cog — alert-first content moderation.

Phase 2 posture: WATCH AND REPORT. With the default configuration this cog
never deletes a message, never times anyone out — it posts alerts to a
private mod channel and collects human verdicts (✅ confirmed / ❌ false
positive) that become the calibration data for any future enforcement.

Configuration (env / secrets):
    MOD_ENABLED=false            master switch for this cog
    MOD_DRY_RUN=true             alert-only; no automatic actions ever
    MOD_ALERT_CHANNEL_ID=        REQUIRED: private channel for alerts
    MOD_PING_ROLE_ID=            optional role ID to @mention on each alert
    MOD_CHANNELS=                REQUIRED: comma-separated channel IDs to
                                 watch (allowlist — empty watches nothing)
    MOD_IGNORED_ROLES=           comma-separated role IDs exempt from scans
    MOD_MIN_CONFIDENCE=0.75      floor for any (future) automatic action
    MOD_ALERT_MIN_CONFIDENCE=0.0 suppress non-forced alerts below this
                                 confidence (hate_speech/doxxing/self_harm/
                                 violence and blocklist hits always alert)
    MOD_IGNORED_CATEGORIES=      comma-separated categories to never alert on
                                 (e.g. misinformation,spam); blocklist hits
                                 are exempt
    MOD_AUTO_DELETE=false        Phase 3: allow auto-delete   (needs MOD_DRY_RUN=false)
    MOD_AUTO_TIMEOUT=false       Phase 3: allow auto-timeout  (needs MOD_DRY_RUN=false)
    MOD_TIMEOUT_MINUTES=10       base auto-timeout duration
    MOD_MIN_MESSAGE_LENGTH=6     skip the LLM for shorter messages (regex
                                 PII/slur scans still run on everything)
    MOD_USER_COOLDOWN_SECONDS=20 per-user LLM-scan cooldown
    MOD_RETENTION_DAYS=90        stored excerpts are purged after this

    Trust tiers (new -> member -> veteran by tenure; trusted/creator by role):
    MOD_MEMBER_DAYS=30           tenure for the 'member' tier
    MOD_VETERAN_DAYS=365         tenure for the 'veteran' tier
    MOD_TRUSTED_ROLES=           role IDs for the 'trusted' staff class
    MOD_CREATOR_ROLES=           role IDs for the 'creator' class
    MOD_RECLAIMED_TIERS=veteran,trusted,creator
                                 tiers whose deny-list hits are adjudicated
                                 with context (reclaimed in-group language)
                                 instead of auto-alerting; attack/uncertain/
                                 model-down still alert

LLM analysis additionally requires AI_ENABLED=true and
AI_MODERATION_ENABLED=true (see ai/config.py). Moderation inference is
local-only: the Gemini fallback is hard-disabled for this feature. Without
the LLM the cog still alerts on regex PII hits and blocklisted slurs.

hate_speech / doxxing / self_harm / violence and every kick/ban proposal
always page a human — they are never auto-actioned in any configuration.
"""

import logging
import os
import re
import time
from collections import deque
from datetime import timedelta

import discord
from discord.ext import commands, tasks
from discord import app_commands

from utils import metrics

logger = logging.getLogger(__name__)

CATEGORY_COLORS = {
    'hate_speech': 0xD32F2F,
    'doxxing': 0xC2185B,
    'self_harm': 0x7B1FA2,
    'violence': 0xE64A19,
    'harassment': 0xF57C00,
    'sexual_content': 0xE91E63,
    'pii_exposure': 0x00838F,
    'social_engineering': 0x5D4037,
    'spam': 0x616161,
    'misinformation': 0x455A64,
    'raid': 0xB71C1C,
    'evasion': 0x37474F,
    'prompt_injection': 0x6A1B9A,
    'unknown': 0x9E9E9E,
}


def _env(name: str, default: str = None) -> str:
    """Env lookup that also consults the secrets manager (Doppler/AWS/Vault)
    for MOD_* keys — same layering as ai/config.py uses for AI_* keys."""
    value = os.getenv(name)
    if value is None and name.startswith('MOD_'):
        from utils.secrets import get_secret
        value = get_secret('MOD', name[4:])
    return value if value is not None else default


def _env_bool(name: str, default: bool) -> bool:
    value = _env(name)
    if value is None:
        return default
    return str(value).strip().lower() in ('1', 'true', 'yes', 'on')


def _env_ids(name: str) -> set:
    raw = _env(name, '')
    return {int(part) for part in re.findall(r'\d{5,}', raw)}


class ReviewButton(discord.ui.DynamicItem[discord.ui.Button],
                   template=r'modact:(?P<pending_id>[0-9]+):(?P<verb>approve|deny)'):
    """Persistent review button — survives bot restarts because the pending
    action id lives in the custom_id, not in process memory."""

    def __init__(self, pending_id: int, verb: str):
        style = discord.ButtonStyle.danger if verb == 'approve' else discord.ButtonStyle.secondary
        label = 'Approve action' if verb == 'approve' else 'Dismiss (false positive)'
        super().__init__(discord.ui.Button(
            style=style, label=label,
            custom_id=f'modact:{pending_id}:{verb}',
        ))
        self.pending_id = pending_id
        self.verb = verb

    @classmethod
    async def from_custom_id(cls, interaction, item, match):
        return cls(int(match['pending_id']), match['verb'])

    async def callback(self, interaction: discord.Interaction):
        # Logged on arrival: when a moderator reports "the button timed out",
        # the absence of this line means the click never reached the bot
        # (dropped gateway event), which is a different fault from a slow or
        # failing handler. Without it the logs are silent either way.
        logger.info('Review button %s:%s clicked by %s',
                    self.pending_id, self.verb, interaction.user)
        cog = interaction.client.get_cog('AIModeration')
        if cog is None:
            await interaction.response.send_message('Moderation cog is not loaded.', ephemeral=True)
            return
        await cog.handle_review_decision(interaction, self.pending_id, self.verb)


class AIModeration(commands.Cog):
    """Alert-first AI moderation."""

    def __init__(self, bot):
        self.bot = bot
        self.enabled = _env_bool('MOD_ENABLED', False)
        self.dry_run = _env_bool('MOD_DRY_RUN', True)
        self.auto_delete = _env_bool('MOD_AUTO_DELETE', False)
        self.auto_timeout = _env_bool('MOD_AUTO_TIMEOUT', False)
        self.min_confidence = float(_env('MOD_MIN_CONFIDENCE', '0.75'))
        self.alert_min_confidence = float(_env('MOD_ALERT_MIN_CONFIDENCE', '0.0'))
        self.ignored_categories = {
            c.strip().lower() for c in _env('MOD_IGNORED_CATEGORIES', '').split(',') if c.strip()
        }
        self.timeout_minutes = int(_env('MOD_TIMEOUT_MINUTES', '10'))
        self.min_message_length = int(_env('MOD_MIN_MESSAGE_LENGTH', '6'))
        self.user_cooldown = float(_env('MOD_USER_COOLDOWN_SECONDS', '20'))
        self.retention_days = int(_env('MOD_RETENTION_DAYS', '90'))

        alert_channel = _env('MOD_ALERT_CHANNEL_ID', '')
        self.alert_channel_id = int(alert_channel) if alert_channel.isdigit() else None
        ping_role = _env('MOD_PING_ROLE_ID', '')
        self.ping_role_id = int(ping_role) if ping_role.isdigit() else None
        self.watched_channels = _env_ids('MOD_CHANNELS')
        self.ignored_roles = _env_ids('MOD_IGNORED_ROLES')

        # Trust tiers: tenure-based (new -> member -> veteran) plus explicit
        # role-based classes for trusted staff and content creators.
        self.trusted_roles = _env_ids('MOD_TRUSTED_ROLES')
        self.creator_roles = _env_ids('MOD_CREATOR_ROLES')
        self.member_days = int(_env('MOD_MEMBER_DAYS', '30'))
        self.veteran_days = int(_env('MOD_VETERAN_DAYS', '365'))
        # Tiers whose deny-list hits get context adjudication (reclaimed
        # in-group language) instead of an automatic hate_speech alert.
        self.reclaimed_tiers = {
            t.strip().lower() for t in
            _env('MOD_RECLAIMED_TIERS', 'veteran,trusted,creator').split(',')
            if t.strip()
        }
        # Community profile: what counts as normal talk here (ai/features/
        # profiles.py). It supplies the model's community context, per-category
        # alert thresholds, and which context checks are worth a model call.
        from ai.features.profiles import get_profile
        self.profile = get_profile(_env('MOD_PROFILE', 'general'))

        # Above this confidence a context adjudication may no longer clear a
        # flag. Set just above the second stage's ordinary 0.85-0.9 band —
        # borderline calls ('Bitch?' between friends) stay adjudicable, a
        # 0.95 conviction does not.
        self.leniency_max_confidence = float(
            _env('MOD_LENIENCY_MAX_CONFIDENCE', '0.95'))

        self.db = None
        self.analyzer = None
        self._user_last_scan = {}          # user_id -> monotonic time
        self._context = {}                 # channel_id -> deque of recent messages
        self._scan_count = 0
        self._alert_count = 0

        if not self.enabled:
            logger.info('AI moderation disabled (MOD_ENABLED=false)')
            return
        if not self.alert_channel_id:
            logger.error('MOD_ENABLED=true but MOD_ALERT_CHANNEL_ID is not set — moderation stays off')
            self.enabled = False
            return
        if not self.watched_channels:
            logger.error('MOD_ENABLED=true but MOD_CHANNELS is empty — moderation watches nothing until channels are allowlisted')
            self.enabled = False
            return

    async def cog_load(self):
        self.bot.add_dynamic_items(ReviewButton)
        if not self.enabled:
            return
        from utils.database import get_database
        from ai.manager import get_ai_manager
        from ai.features.moderation import ModerationAnalyzer
        self.db = await get_database()
        self.analyzer = ModerationAnalyzer(await get_ai_manager())
        self.retention_purge.start()
        mode = 'DRY-RUN (alert only)' if self.dry_run else 'ENFORCING'
        logger.info(
            f'AI moderation active [{mode}]: watching {len(self.watched_channels)} channel(s), '
            f'alerts -> {self.alert_channel_id}'
        )

    async def cog_unload(self):
        if self.retention_purge.is_running():
            self.retention_purge.cancel()
        if self.db:
            await self.db.close()

    # ------------------------------------------------------------------ scan

    def _trust_tier(self, member) -> str:
        """new -> member -> veteran by tenure; trusted/creator by role.
        Fully exempt users (mods) never reach here — MOD_IGNORED_ROLES
        gates them out in _eligible(). Shared with the newcomer helper,
        which asks the same question for a friendlier reason."""
        from utils.trust import trust_tier
        return trust_tier(
            member,
            member_days=self.member_days, veteran_days=self.veteran_days,
            trusted_roles=self.trusted_roles, creator_roles=self.creator_roles,
        )

    def _eligible(self, message) -> bool:
        """Shared gating for new and edited messages."""
        if message.author.bot or not message.guild:
            return False
        if message.channel.id not in self.watched_channels:
            return False
        if message.channel.id == self.alert_channel_id:
            return False
        if isinstance(message.author, discord.Member):
            if any(role.id in self.ignored_roles for role in message.author.roles):
                return False
        return True

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not self.enabled or self.analyzer is None:
            return
        if not self._eligible(message):
            return

        content = message.content or ''
        if not content.strip():
            return

        try:
            await self._scan_message(message, content)
        except Exception:
            logger.exception('Moderation scan failed')

    @commands.Cog.listener()
    async def on_raw_message_edit(self, payload: discord.RawMessageUpdateEvent):
        """Edits are an evasion vector: post clean, edit in the slur. The RAW
        event catches edits to messages that predate the bot's cache."""
        if not self.enabled or self.analyzer is None:
            return
        if payload.channel_id not in self.watched_channels:
            return

        # Embed unfurls and pin/flag changes fire MESSAGE_UPDATE without a
        # content field — never re-scan those (every posted link unfurls).
        new_content = payload.data.get('content')
        if new_content is None or not new_content.strip():
            return
        cached = payload.cached_message
        if cached is not None and cached.content == new_content:
            return

        message = getattr(payload, 'message', None)
        if message is None:
            channel = self.bot.get_channel(payload.channel_id)
            if channel is None:
                return
            try:
                message = await channel.fetch_message(payload.message_id)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                return
        if not self._eligible(message):
            return

        try:
            await self._scan_message(message, new_content, edited=True)
        except Exception:
            logger.exception('Moderation edit-scan failed')

    async def _scan_message(self, message: discord.Message, content: str,
                            edited: bool = False):
        from ai.features.moderation import (
            ModerationResult, classify_ip_context, decide, pre_scan_pii,
        )
        from ai.guardrails import (
            find_blocked_terms, find_dogwhistles, find_evasion_markers,
            find_injection_markers, sanitize_input,
        )

        context = self._context_for(message.channel.id)

        pii = pre_scan_pii(content)
        denylist_hits = find_blocked_terms(content)
        dogwhistle_hits = find_dogwhistles(content)
        # A message that tries to steer a model does not get the benefit of a
        # model's context call about itself — see _leniency_allowed.
        injection_markers = find_injection_markers(content)
        evasion_markers = find_evasion_markers(content)
        attack_markers = ([f'injection: {m}' for m in injection_markers]
                          + [f'evasion: {m}' for m in evasion_markers])

        # Short messages skip the LLM unless a regex already found something
        # A message with no letters (emoji spam, a bare mention, kaomoji)
        # has nothing for a language model to classify — live testing showed
        # such messages picking up spurious verdicts. Regex scans still ran.
        has_letters = any(ch.isalpha() for ch in content)
        run_llm = ((len(content) >= self.min_message_length and has_letters)
                   or bool(pii) or bool(denylist_hits) or bool(dogwhistle_hits)
                   or bool(attack_markers))

        # Per-user cooldown applies to LLM scans only; regex hits always proceed
        now = time.monotonic()
        if run_llm and not pii and not denylist_hits and not dogwhistle_hits:
            # None, not 0: time.monotonic() counts from boot, so a 0 default
            # made every user look recently-scanned for the first
            # MOD_USER_COOLDOWN_SECONDS after a reboot.
            last = self._user_last_scan.get(message.author.id)
            if last is not None and now - last < self.user_cooldown:
                run_llm = False
            else:
                self._user_last_scan[message.author.id] = now
                if len(self._user_last_scan) > 5000:
                    self._user_last_scan.clear()

        # Track context AFTER deciding, so a message never appears in its own context
        result = None
        if run_llm:
            infraction_count = await self.db.get_user_infraction_count(
                message.guild.id, message.author.id,
            )
            self._scan_count += 1
            metrics.MOD_SCANS.inc()
            result = await self.analyzer.analyze(
                content,
                message.author.display_name,
                channel_name=getattr(message.channel, 'name', ''),
                context_messages=list(context),
                infraction_count=infraction_count,
            )

        context.append(f"{message.author.display_name}: {sanitize_input(content, 200)}")

        # Dog-whistle watchlist (ADL coded terms with benign readings, e.g.
        # ham radio's 73/88 signoff): adjudicate BEFORE the safe-path early
        # return — the primary model usually reads coded signals as safe.
        # hateful -> hate_speech; unclear -> review; benign/mention pass.
        if dogwhistle_hits and not (result is not None and result.denylist_hit):
            verdict = await self.analyzer.adjudicate(
                'dogwhistle', content, message.author.display_name,
                context_messages=list(context)[:-1],
                note=', '.join(dogwhistle_hits),
            )
            metrics.MOD_ADJUDICATIONS.labels(kind='dogwhistle', outcome=verdict).inc()
            if verdict == 'hateful':
                result = ModerationResult(
                    False, 'hate_speech', 0.9,
                    f"coded hate signal ({', '.join(dogwhistle_hits)}) — context check: hateful",
                    'review', pii,
                )
            elif verdict == 'uncertain' and (result is None or result.is_safe):
                result = ModerationResult(
                    False, 'evasion', 0.5,
                    f"possible coded signal ({', '.join(dogwhistle_hits)}) — context unclear",
                    'review', pii,
                )
            elif (verdict in ('benign', 'mention')
                  and result is not None and not result.is_safe
                  and result.category in ('hate_speech', 'harassment')
                  and self._leniency_allowed(result, injection_markers)):
                # The context-aware adjudicator overrules a context-blind
                # model verdict on a watchlisted trope: red-team labels
                # showed jokes QUESTIONING a trope ("but why jewish?")
                # flagged as hate while assertions of it were confirmed.
                logger.info('Watchlist context check (%s) overrides model %s verdict',
                            verdict, result.category)
                result = ModerationResult(
                    True, 'safe', 0.8,
                    f"watchlist context check: {verdict}", 'none', pii,
                )

        if result is None or result.is_safe:
            # Regex PII on an otherwise-safe message still deserves an alert
            if pii:
                result = ModerationResult(
                    False, 'pii_exposure', 0.9,
                    f"regex detected: {', '.join(pii)}", 'review', pii,
                )
            elif attack_markers:
                # An attack carrying no slur and no PII used to pass silently:
                # the payload is the point, and "someone is probing the bot"
                # is worth a moderator's eyes and a label of its own.
                result = ModerationResult(
                    False, 'prompt_injection', 0.7,
                    f"filter/model manipulation attempt ({', '.join(attack_markers)})",
                    'review', pii,
                )
            else:
                return
        elif pii and not result.pii_detected:
            result.pii_detected = pii

        if (result.category in self.ignored_categories
                and not result.denylist_hit):
            return

        tier = self._trust_tier(message.author)

        # IP addresses in a security community are indicators, lab kit, and
        # log output far more often than they are anyone's home connection.
        # The cheap classifier settles most of it; only the ambiguous middle
        # costs a model call.
        if self.profile.enables('ip_address') and 'ip_address' in result.pii_detected:
            ip_context = classify_ip_context(content)
            if ip_context == 'ambiguous':
                ip_context = await self.analyzer.adjudicate(
                    'ip_address', content, message.author.display_name,
                    context_messages=list(context)[:-1],
                )
                metrics.MOD_ADJUDICATIONS.labels(
                    kind='ip_address', outcome=ip_context).inc()
                # 'uncertain' reads as technical here, and only here: in a
                # room where most IPs are indicators, alerting on every
                # unclear one trains moderators to skim past alerts. A real
                # IP-doxx carries attribution the classifier catches first.
                ip_context = 'technical' if ip_context != 'personal' else 'personal'
            if ip_context == 'technical':
                result.pii_detected = [p for p in result.pii_detected
                                       if p != 'ip_address']
                if not result.pii_detected and result.category in ('pii_exposure', 'safe'):
                    logger.info('IP treated as technical (%s profile)', self.profile.name)
                    return

        # Attack techniques are the subject matter here: explaining how
        # doxxing or phishing works is a lesson, doing it to someone is not.
        if (self.profile.enables('security_topic')
                and result.category in ('doxxing', 'social_engineering')
                and not result.denylist_hit
                and self._leniency_allowed(result, injection_markers)):
            verdict = await self.analyzer.adjudicate(
                'security_topic', content, message.author.display_name,
                context_messages=list(context)[:-1],
            )
            metrics.MOD_ADJUDICATIONS.labels(kind='security_topic', outcome=verdict).inc()
            if verdict == 'educational':
                logger.info('Security topic adjudicated educational — suppressed')
                return
            if verdict == 'operational':
                result.reason += ' · security check: operational (real target)'

        # Lockpicking, range days, and radio gear are hobbies, not threats.
        if (self.profile.enables('weapons_hobby')
                and result.category == 'violence'
                and not result.denylist_hit
                and self._leniency_allowed(result, injection_markers)):
            verdict = await self.analyzer.adjudicate(
                'weapons_hobby', content, message.author.display_name,
                context_messages=list(context)[:-1],
            )
            metrics.MOD_ADJUDICATIONS.labels(kind='weapons_hobby', outcome=verdict).inc()
            if verdict == 'hobby':
                logger.info('Weapons/hobby context adjudicated hobby — suppressed')
                return

        # Reclaimed in-group language: for tenured/trusted tiers a deny-list
        # hit — or a MODEL hate/harassment verdict (red-team labels: 'Bitch?'
        # and campy queer banter flagged harassment) — is adjudicated with
        # context instead of auto-alerting. 'attack'/'uncertain'/model-down
        # all still alert (fail open); new users always get the strict path.
        model_hate = (not result.denylist_hit
                      and result.category in ('hate_speech', 'harassment'))
        if (result.denylist_hit or model_hate) and tier in self.reclaimed_tiers:
            verdict = await self.analyzer.adjudicate(
                'reclaimed_slur', content, message.author.display_name,
                context_messages=list(context)[:-1],
            )
            metrics.MOD_ADJUDICATIONS.labels(kind='reclaimed_slur', outcome=verdict).inc()
            if verdict == 'banter' and not self._leniency_allowed(result, injection_markers):
                verdict = 'uncertain'
            if verdict == 'banter':
                logger.info('Deny-list hit adjudicated as in-group banter (%s tier)', tier)
                return
            result.reason += f' · in-group check: {verdict}'

        # Public/famous addresses are not doxxing — adjudicate address-driven
        # flags for every tier ("the White House is at 1600 Pennsylvania
        # Ave" once alerted). 'private'/'uncertain'/model-down still alert.
        address_driven = ('address' in result.pii_detected
                          or (result.category == 'doxxing' and not result.denylist_hit))
        if address_driven:
            verdict = await self.analyzer.adjudicate(
                'address', content, message.author.display_name,
                context_messages=list(context)[:-1],
            )
            metrics.MOD_ADJUDICATIONS.labels(kind='address', outcome=verdict).inc()
            if verdict == 'public':
                result.pii_detected = [p for p in result.pii_detected if p != 'address']
                if result.category == 'doxxing':
                    logger.info('Address flag adjudicated as public/famous — suppressed')
                    return
                if not result.pii_detected and result.category in ('pii_exposure', 'safe'):
                    return

        decision = decide(
            result,
            dry_run=self.dry_run,
            min_confidence=self.min_confidence,
            auto_delete=self.auto_delete,
            auto_timeout=self.auto_timeout,
            # Per-category floor from the profile: categories that are mostly
            # shop talk in this community need more confidence to page anyone.
            # Forced-review categories ignore this floor entirely.
            alert_min_confidence=self.profile.threshold_for(
                result.category, self.alert_min_confidence),
        )
        if not decision.alert:
            return

        await self._handle_detection(message, content, result, decision,
                                     edited=edited, tier=tier,
                                     attack_markers=attack_markers)

    def _leniency_allowed(self, result, injection_markers) -> bool:
        """Whether a context adjudication may talk a flag DOWN to safe.

        Two things forfeit that leniency, both from mod-labeled replays:

        1. Prompt-injection markers in the message. The adjudicator is the
           same kind of model the message is trying to steer, and a message
           pairing a real hate trope with 'forget all prior commands' was
           read as a harmless test and cleared.
        2. A high-confidence MODEL verdict. Adjudication exists to rescue
           borderline calls (a joke questioning a trope), not to overturn a
           verdict the second-opinion stage already confirmed. Deny-list
           hits are exempt: their 0.95+ is regex certainty about the word,
           which is exactly the case reclaimed-language review is for.
        """
        if injection_markers:
            logger.info('Leniency withheld — injection markers present: %s',
                        ', '.join(injection_markers))
            return False
        if (result is not None and not result.denylist_hit
                and result.confidence >= self.leniency_max_confidence):
            logger.info('Leniency withheld — %s verdict at confidence %.2f',
                        result.category, result.confidence)
            return False
        return True

    def _context_for(self, channel_id: int) -> deque:
        context = self._context.get(channel_id)
        if context is None:
            if len(self._context) > 100:
                self._context.pop(next(iter(self._context)))
            context = deque(maxlen=5)
            self._context[channel_id] = context
        return context

    # --------------------------------------------------------------- actions

    async def _handle_detection(self, message, content, result, decision,
                                edited=False, tier='', attack_markers=()):
        cfg_model = ''
        try:
            from ai import config as ai_config
            cfg_model = ai_config.get_feature_config('moderation').model
        except Exception:
            pass

        action_taken = 'none'
        if decision.auto_action != 'none':
            action_taken = await self._execute_auto_action(message, decision.auto_action)

        infraction_id = await self.db.add_infraction(
            guild_id=message.guild.id,
            channel_id=message.channel.id,
            message_id=message.id,
            user_id=message.author.id,
            username=str(message.author),
            category=result.category,
            confidence=result.confidence,
            proposed_action=result.suggested_action,
            action_taken=action_taken,
            excerpt=content,
            model=cfg_model,
            dry_run=self.dry_run,
        )
        self._alert_count += 1
        metrics.MOD_ALERTS.labels(category=result.category).inc()
        if action_taken not in ('none', 'failed'):
            metrics.MOD_ACTIONS.labels(action=action_taken.split(':')[0]).inc()
        if attack_markers:
            logger.info('Attack markers on alert #%s: %s',
                        infraction_id, ', '.join(attack_markers))
            for marker in attack_markers:
                metrics.MOD_ATTACK_MARKERS.labels(
                    marker=marker.split(':')[0].strip()).inc()
        await self._post_alert(message, content, result, decision, infraction_id,
                               action_taken, edited=edited, tier=tier,
                               attack_markers=attack_markers)

    async def _execute_auto_action(self, message, action: str) -> str:
        """Phase 3 path — reachable only with MOD_DRY_RUN=false plus the
        per-action flag, and never for forced-review categories."""
        try:
            if action == 'delete':
                await message.delete()
                return 'delete'
            if action == 'timeout' and isinstance(message.author, discord.Member):
                duration = timedelta(minutes=min(self.timeout_minutes, 60))
                await message.author.timeout(duration, reason='AI moderation (auto)')
                return f'timeout:{int(duration.total_seconds() // 60)}m'
        except discord.Forbidden:
            logger.warning(f'Missing permission to {action} in #{message.channel}')
        except Exception as e:
            logger.error(f'Auto-action {action} failed: {type(e).__name__}')
        return 'failed'

    async def _post_alert(self, message, content, result, decision,
                          infraction_id, action_taken, edited=False, tier='',
                          attack_markers=()):
        channel = self.bot.get_channel(self.alert_channel_id)
        if channel is None:
            logger.error(f'Alert channel {self.alert_channel_id} not found')
            return

        from ai.endpoints import scrub_addresses

        history = await self.db.get_user_history(message.guild.id, message.author.id, limit=4)
        prior = [h for h in history if h.get('created_at')]

        embed = discord.Embed(
            title=f"🚨 {result.category.replace('_', ' ').title()}",
            color=CATEGORY_COLORS.get(result.category, 0x9E9E9E),
            description=(
                f"**User:** {message.author.mention} ({message.author})\n"
                f"**Channel:** {message.channel.mention} — [jump to message]({message.jump_url})\n"
                f"**Confidence:** {result.confidence:.0%}"
                + (" · **blocklist hit**" if result.denylist_hit else "")
                + (" · ✏️ **edited message**" if edited else "")
                + (f"\n**User trust:** {tier}" if tier else "")
            ),
        )
        excerpt = content[:400] + ('…' if len(content) > 400 else '')
        embed.add_field(name='Message', value=f">>> {excerpt}", inline=False)
        # Reasons quote whatever the model or a connection error handed us,
        # which is how an inference host's address ends up in a channel.
        embed.add_field(name='Model reasoning',
                        value=scrub_addresses(result.reason)[:1000] or '—', inline=False)
        if result.pii_detected:
            embed.add_field(name='PII detected', value=', '.join(result.pii_detected), inline=True)
        if attack_markers:
            # Named on the alert so "someone is probing the filters" is a
            # thing a moderator can see and label, not an inference.
            embed.add_field(name='🎣 Attack markers',
                            value='\n'.join(f'• {m}' for m in attack_markers)[:1000],
                            inline=False)
        embed.add_field(name='Proposed action', value=result.suggested_action, inline=True)
        embed.add_field(
            name='Mode',
            value=('dry-run' if self.dry_run else f'action taken: {action_taken}'),
            inline=True,
        )
        if len(prior) > 1:
            lines = [
                f"{h['category']} ({h['confidence']:.0%}, {h['human_verdict'] or 'unlabeled'})"
                for h in prior[1:]
            ]
            embed.add_field(name=f'Prior flags ({len(lines)})', value='\n'.join(lines)[:1000], inline=False)
        view = None
        if decision.requires_human:
            pending_id = await self.db.add_pending_action(infraction_id, result.suggested_action)
            view = discord.ui.View(timeout=None)
            view.add_item(ReviewButton(pending_id, 'approve'))
            view.add_item(ReviewButton(pending_id, 'deny'))

        # One labelling affordance per alert. Buttons and reactions both used
        # to appear, which meant two ways to say the same thing and three
        # extra REST calls per alert (send + two add_reaction) competing for
        # the channel's rate limit with the clicks moderators were waiting on.
        embed.set_footer(text=(
            f'#{infraction_id} · buttons record the decision — labels tune the system'
            if view is not None else
            f'#{infraction_id} · ✅ confirm / ❌ false positive — labels tune the system'
        ))

        ping_content = None
        allowed = None
        if self.ping_role_id:
            ping_content = f'<@&{self.ping_role_id}>'
            allowed = discord.AllowedMentions(
                everyone=False, users=False,
                roles=[discord.Object(id=self.ping_role_id)],
            )

        try:
            alert = await channel.send(
                content=ping_content, embed=embed, view=view,
                allowed_mentions=allowed,
            )
            if decision.requires_human:
                await self.db.set_review_message(pending_id, alert.id)
            else:
                await alert.add_reaction('✅')
                await alert.add_reaction('❌')
        except discord.Forbidden:
            logger.error('Missing permission to post in the moderation alert channel')

    # ------------------------------------------------------ human decisions

    async def handle_review_decision(self, interaction: discord.Interaction,
                                     pending_id: int, verb: str):
        """Answer a review click in ONE Discord round trip.

        The first version deferred, wrote to the database, edited the alert
        and then sent an ephemeral confirmation — three REST calls, of which
        `defer()` on a component interaction shows the moderator nothing at
        all. Under a burst of labelling those calls queue behind the alert
        channel's edit rate limit, and measured latencies ran 600ms to 11s
        with no visible feedback, so moderators clicked again. And again.

        The database writes are local SQLite (0.3ms measured on the box), so
        they can happen BEFORE the reply. That makes the reply itself the ACK:
        one `edit_message` posts the resolution and removes the buttons, so
        there is nothing left to double-click. Only the enforcing path, which
        calls Discord to ban or time someone out, still needs a defer.
        """
        started = time.monotonic()

        if not interaction.user.guild_permissions.moderate_members:
            await interaction.response.send_message(
                'You need the Moderate Members permission to review moderation actions.',
                ephemeral=True,
            )
            return

        pending = await self.db.get_pending_action(pending_id)
        if pending is None:
            await interaction.response.send_message(
                'This review no longer exists.', ephemeral=True)
            return

        status = 'approved' if verb == 'approve' else 'denied'
        claimed = await self.db.resolve_pending_action(pending_id, status, interaction.user.id)
        if not claimed:
            # A second click on a button that has not disappeared from this
            # moderator's client yet — say so quietly, change nothing.
            await interaction.response.send_message(
                'Already decided.', ephemeral=True)
            return

        verdict = 'confirmed' if verb == 'approve' else 'false_positive'
        await self.db.set_human_verdict(pending['infraction_id'], verdict, interaction.user.id)
        metrics.MOD_VERDICTS.labels(verdict=verdict).inc()

        # Enforcing an approved action means calling Discord (ban/timeout),
        # which can outlast the 3s response window — ACK first in that case.
        deferred = False
        outcome = 'dismissed as false positive'
        if verb == 'approve':
            if self.dry_run:
                outcome = 'confirmed (dry-run: no action executed)'
            else:
                await interaction.response.defer()
                deferred = True
                outcome = await self._execute_approved_action(pending)

        embed = (interaction.message.embeds[0] if interaction.message.embeds
                 else discord.Embed())
        embed.add_field(
            name='Resolution',
            value=f'{outcome} — by {interaction.user.mention}',
            inline=False,
        )
        try:
            if deferred:
                await interaction.message.edit(embed=embed, view=None)
            else:
                await interaction.response.edit_message(embed=embed, view=None)
        except discord.HTTPException as e:
            # The label is already recorded; only the visible confirmation
            # failed. 10062 = the click reached us after Discord gave up.
            logger.error('Review %s recorded but the alert could not be updated '
                         '(code %s): %s', pending_id, getattr(e, 'code', '?'), e)

        logger.info('Review %s resolved as %s by %s in %.0fms',
                    pending_id, status, interaction.user,
                    (time.monotonic() - started) * 1000)

    async def _execute_approved_action(self, pending: dict) -> str:
        guild = self.bot.get_guild(pending['guild_id'])
        if guild is None:
            return 'guild not found'
        action = pending['proposed_action']
        try:
            member = guild.get_member(pending['user_id']) or await guild.fetch_member(pending['user_id'])
        except discord.NotFound:
            member = None

        try:
            if action == 'delete':
                channel = guild.get_channel(pending['channel_id'])
                if channel:
                    msg = await channel.fetch_message(pending['message_id'])
                    await msg.delete()
                    return 'message deleted'
                return 'channel not found'
            if action == 'timeout' and member:
                await member.timeout(timedelta(minutes=self.timeout_minutes),
                                     reason='AI moderation (moderator approved)')
                return f'timed out {self.timeout_minutes}m'
            if action == 'kick' and member:
                await member.kick(reason='AI moderation (moderator approved)')
                return 'kicked'
            if action == 'ban' and member:
                await member.ban(reason='AI moderation (moderator approved)', delete_message_days=0)
                return 'banned'
            if action in ('warn', 'review', 'none'):
                return 'confirmed (no direct action)'
            return f'{action}: user not found'
        except discord.Forbidden:
            return f'{action} failed: missing permission'
        except discord.NotFound:
            return f'{action} failed: message already gone'
        except Exception as e:
            logger.error(f'Approved action {action} failed: {type(e).__name__}')
            return f'{action} failed'

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        """✅/❌ on an alert = calibration label (works after restarts too)."""
        if not self.enabled or self.db is None:
            return
        if payload.channel_id != self.alert_channel_id:
            return
        if str(payload.emoji) not in ('✅', '❌'):
            return
        if payload.member is None or payload.member.bot:
            return
        if not payload.member.guild_permissions.moderate_members:
            return

        infraction = await self.db.find_infraction_by_alert(payload.message_id)
        if infraction is None:
            return
        verdict = 'confirmed' if str(payload.emoji) == '✅' else 'false_positive'
        await self.db.set_human_verdict(infraction['id'], verdict, payload.user_id)
        metrics.MOD_VERDICTS.labels(verdict=verdict).inc()
        logger.info('Alert #%s labeled %s by %s (reaction)',
                    infraction['id'], verdict, payload.user_id)

        # Say so on the alert. Recording a label silently is indistinguishable
        # from the bot ignoring the click, which is how a working label gets
        # reported as "nothing happened".
        try:
            channel = self.bot.get_channel(payload.channel_id)
            message = channel and await channel.fetch_message(payload.message_id)
            if message and message.embeds:
                embed = message.embeds[0]
                embed.set_footer(
                    text=f"#{infraction['id']} · labeled "
                         f"{'✅ confirmed' if verdict == 'confirmed' else '❌ false positive'} "
                         f"by {payload.member.display_name}",
                )
                await message.edit(embed=embed)
        except Exception:
            logger.exception('Could not mark alert as labeled')

    # ------------------------------------------------------------- commands

    mod_group = app_commands.Group(
        name='mod', description='AI moderation controls',
        default_permissions=discord.Permissions(moderate_members=True),
    )

    @mod_group.command(name='status', description='Show AI moderation status')
    async def mod_status(self, interaction: discord.Interaction):
        embed = discord.Embed(title='🛡️ AI Moderation Status', color=0x1793D1)
        embed.add_field(name='Enabled', value=str(self.enabled), inline=True)
        embed.add_field(name='Mode', value='dry-run (alert only)' if self.dry_run else 'enforcing', inline=True)
        embed.add_field(name='Watched channels', value=str(len(self.watched_channels)), inline=True)
        embed.add_field(name='Community profile', value=self.profile.name, inline=True)
        embed.add_field(name='LLM scans', value=str(self._scan_count), inline=True)
        embed.add_field(name='Alerts', value=str(self._alert_count), inline=True)
        if self.analyzer is not None:
            try:
                from ai.endpoints import describe_provider_status
                from ai.manager import get_ai_manager
                status = (await get_ai_manager()).status()
                # This embed goes to a Discord channel, so it names providers
                # and never addresses — see ai/endpoints.py.
                lines = [describe_provider_status('Ollama', status['ollama_hosts'])]
                if status.get('gemini_available'):
                    lines.append('Gemini: configured')
                embed.add_field(name='Inference', value='\n'.join(lines), inline=False)
                embed.add_field(name='Queue', value=f"{status['queue_pending']} pending / {status['queue_rejected']} dropped", inline=True)
            except Exception:
                logger.exception('Could not render AI status')
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @mod_group.command(name='stats', description='Per-category precision from moderator labels')
    @app_commands.describe(days='Window in days (default 14)')
    async def mod_stats(self, interaction: discord.Interaction, days: int = 14):
        if self.db is None:
            await interaction.response.send_message('Moderation database not active.', ephemeral=True)
            return
        stats = await self.db.calibration_stats(interaction.guild_id, days=days)
        if not stats:
            await interaction.response.send_message(f'No detections in the last {days} days.', ephemeral=True)
            return
        total = sum(r['total'] for r in stats.values())
        confirmed = sum(r['confirmed'] for r in stats.values())
        false_pos = sum(r['false_positives'] for r in stats.values())
        labeled = confirmed + false_pos
        embed = discord.Embed(title=f'📊 Moderation calibration — last {days}d', color=0x1793D1)
        embed.description = (
            f"**Live alert accuracy: "
            f"{f'{confirmed / labeled:.0%}' if labeled else 'n/a — label some alerts with ✅/❌'}**"
            f" ({confirmed}✅ / {false_pos}❌ of {total} alerts, "
            f"{f'{labeled / total:.0%}' if total else '0%'} labeled)\n"
            f"Use `/mod benchmark` for accuracy against the built-in golden test set."
        )
        for category, row in stats.items():
            labeled = row['confirmed'] + row['false_positives']
            precision = f"{row['confirmed'] / labeled:.0%}" if labeled else 'n/a'
            embed.add_field(
                name=category,
                value=(f"{row['total']} alerts · {row['confirmed']}✅ {row['false_positives']}❌ "
                       f"{row['unlabeled']} unlabeled · precision {precision}"),
                inline=False,
            )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @mod_group.command(name='pending', description='List moderation reviews nobody has decided yet')
    async def mod_pending(self, interaction: discord.Interaction):
        """Escape hatch for alerts whose buttons went unanswered — a dropped
        interaction leaves the review open with no sign of it in the channel."""
        if self.db is None:
            await interaction.response.send_message('Moderation database not active.', ephemeral=True)
            return
        rows = await self.db.list_pending_actions(interaction.guild_id)
        if not rows:
            await interaction.response.send_message('No open reviews. 🎉', ephemeral=True)
            return

        embed = discord.Embed(
            title=f'⏳ Open reviews ({len(rows)})', color=0xF57C00,
            description='React ✅ / ❌ on the alert, or use its buttons.',
        )
        for row in rows[:10]:
            link = (f"https://discord.com/channels/{interaction.guild_id}/"
                    f"{self.alert_channel_id}/{row['review_message_id']}"
                    if row['review_message_id'] else 'alert message unknown')
            excerpt = ' '.join((row['excerpt'] or '').split())[:70]
            embed.add_field(
                name=f"#{row['infraction_id']} · {row['category']} "
                     f"({row['confidence']:.0%}) · {row['username']}",
                value=f"{excerpt}\n[jump to alert]({link})",
                inline=False,
            )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @mod_group.command(name='benchmark',
                       description='Measure detection accuracy against the built-in golden test set')
    async def mod_benchmark(self, interaction: discord.Interaction):
        """Run the shipped hate/clean golden corpus through the live analyzer
        and report accuracy. One model call per example — takes a few
        minutes and keeps the GPU busy while it runs."""
        if self.analyzer is None:
            await interaction.response.send_message('Moderation is not active.', ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)

        from ai.features.moderation import benchmark_golden
        import time as _time
        started = _time.monotonic()
        try:
            summary = await benchmark_golden(self.analyzer)
        except Exception:
            logger.exception('Golden benchmark failed')
            await interaction.followup.send('Benchmark failed — see bot logs.', ephemeral=True)
            return
        elapsed = _time.monotonic() - started

        embed = discord.Embed(
            title='🎯 Golden-set benchmark',
            color=0x2E7D32 if summary['accuracy'] >= 0.85 else 0xF57C00,
            description=(
                f"**Overall accuracy: {summary['accuracy']:.0%}** "
                f"({summary['total']} labeled examples, {elapsed:.0f}s)\n"
                f"Hate recall: {summary['hate_recall']:.0%} overall · "
                f"{summary['model_recall']:.0%} on slur-free cases (model-only)\n"
                f"Clean false-positive rate: {summary['clean_fp_rate']:.0%}"
            ),
        )
        if summary['misses']:
            lines = [f"• {r['text'][:60]} ({r['note']})" for r in summary['misses'][:6]]
            embed.add_field(name=f"Missed hate ({len(summary['misses'])})",
                            value='\n'.join(lines)[:1000], inline=False)
        if summary['false_positives']:
            lines = [f"• [{r['category']}] {r['text'][:55]}" for r in summary['false_positives'][:6]]
            embed.add_field(name=f"False positives ({len(summary['false_positives'])})",
                            value='\n'.join(lines)[:1000], inline=False)
        embed.set_footer(text='Slur-bearing hate is deny-list-backed (always 100%). '
                              'Grow the corpus in ai/moderation_golden.json.')
        await interaction.followup.send(embed=embed, ephemeral=True)

    @mod_group.command(name='test', description='Run the moderation analyzer on sample text (nothing is stored)')
    @app_commands.describe(text='Text to analyze')
    async def mod_test(self, interaction: discord.Interaction, text: str):
        if self.analyzer is None:
            await interaction.response.send_message('Moderation is not active.', ephemeral=True)
            return
        from ai.endpoints import scrub_addresses

        await interaction.response.defer(ephemeral=True)
        result = await self.analyzer.analyze(text, interaction.user.display_name)
        await interaction.followup.send(
            f"safe={result.is_safe} category={result.category} "
            f"confidence={result.confidence:.2f} action={result.suggested_action}\n"
            f"reason: {scrub_addresses(result.reason)[:500]}",
            ephemeral=True,
        )

    @mod_group.command(name='purge_user', description='Delete all stored moderation data for a user')
    async def mod_purge_user(self, interaction: discord.Interaction, user: discord.User):
        if self.db is None:
            await interaction.response.send_message('Moderation database not active.', ephemeral=True)
            return
        count = await self.db.purge_user(interaction.guild_id, user.id)
        await interaction.response.send_message(
            f'Purged {count} stored record(s) for {user.mention}.', ephemeral=True,
        )

    @tasks.loop(hours=24)
    async def retention_purge(self):
        if self.db is None:
            return
        try:
            removed = await self.db.purge_older_than(self.retention_days)
            if removed:
                logger.info(f'Moderation retention: purged {removed} record(s) older than {self.retention_days}d')
        except Exception:
            logger.exception('Retention purge failed')

    @retention_purge.before_loop
    async def before_retention_purge(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(AIModeration(bot))
    logger.info('AIModeration cog loaded')
