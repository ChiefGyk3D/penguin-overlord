# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
AI Moderation Cog - Real-time content moderation with human-in-the-loop.

Listens to all messages, runs them through the AI moderation analyzer,
and takes tiered actions:
    - Auto-actions (warn, delete, mute/timeout) for clear violations
    - Human-in-the-loop review for severe actions (kick, ban)
    - Offender tracking with persistent SQLite database
    - Configurable mod review channel for escalations

Environment Variables:
    MOD_ENABLED=true                    # Master switch
    MOD_LOG_CHANNEL_ID=123456789        # Channel for mod action logs
    MOD_REVIEW_CHANNEL_ID=123456789     # Channel for human review requests
    MOD_AUTO_DELETE=true                # Auto-delete flagged messages
    MOD_AUTO_TIMEOUT=true               # Auto-timeout for mute/timeout actions
    MOD_DEFAULT_TIMEOUT_MINUTES=10      # Default timeout duration
    MOD_MAX_AUTO_TIMEOUT_MINUTES=60     # Max auto-timeout (longer needs review)
    MOD_IGNORED_CHANNELS=id1,id2        # Channels to skip moderation
    MOD_IGNORED_ROLES=id1,id2           # Roles exempt from moderation
    MOD_MIN_CONFIDENCE=0.7              # Minimum AI confidence to act
    MOD_SCAN_BOTS=false                 # Whether to scan bot messages
"""

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional, List

import discord
from discord.ext import commands
from discord import ui

logger = logging.getLogger(__name__)

# Try to import AI manager
try:
    from ai import get_ai_manager
    AI_SUPPORT = True
except ImportError:
    try:
        from penguin_overlord.ai import get_ai_manager
        AI_SUPPORT = True
    except ImportError:
        AI_SUPPORT = False

# Try to import database
try:
    from utils.database import get_database
    DB_SUPPORT = True
except ImportError:
    try:
        from penguin_overlord.utils.database import get_database
        DB_SUPPORT = True
    except ImportError:
        DB_SUPPORT = False

# Try to import moderation types
try:
    from ai.features.moderation import (
        ModerationCategory, ModerationResult,
        ACTIONS_REQUIRING_REVIEW, ACTION_SEVERITY,
    )
except ImportError:
    try:
        from penguin_overlord.ai.features.moderation import (
            ModerationCategory, ModerationResult,
            ACTIONS_REQUIRING_REVIEW, ACTION_SEVERITY,
        )
    except ImportError:
        ACTIONS_REQUIRING_REVIEW = {'kick', 'ban'}
        ACTION_SEVERITY = {}


def _get_env_list(key: str) -> List[str]:
    """Get a comma-separated env var as a list of strings."""
    val = os.getenv(key, '').strip()
    if not val:
        return []
    return [v.strip() for v in val.split(',') if v.strip()]


# ── Category colors for embeds ────────────────────────────────────────────

CATEGORY_COLORS = {
    'safe': 0x2ECC71,           # Green
    'harassment': 0xE74C3C,     # Red
    'hate_speech': 0xE74C3C,    # Red
    'sexual_content': 0xE91E63, # Pink
    'violence': 0xC0392B,       # Dark red
    'self_harm': 0x9B59B6,      # Purple
    'spam': 0xF39C12,           # Orange
    'misinformation': 0xE67E22, # Dark orange
    'doxxing': 0x000000,        # Black (highest severity)
    'pii_exposure': 0x1ABC9C,   # Teal
    'social_engineering': 0x3498DB,  # Blue
    'raid': 0xC0392B,           # Dark red
    'evasion': 0x95A5A6,        # Gray
    'unknown': 0x7F8C8D,        # Gray
}

CATEGORY_EMOJI = {
    'safe': '✅',
    'harassment': '🎯',
    'hate_speech': '🚫',
    'sexual_content': '🔞',
    'violence': '⚔️',
    'self_harm': '💜',
    'spam': '📧',
    'misinformation': '🤥',
    'doxxing': '🚨',
    'pii_exposure': '🔐',
    'social_engineering': '🎣',
    'raid': '⚡',
    'evasion': '🥷',
    'unknown': '❓',
}

ACTION_EMOJI = {
    'none': '✅',
    'warn': '⚠️',
    'delete': '🗑️',
    'mute': '🔇',
    'timeout': '⏰',
    'kick': '👢',
    'ban': '🔨',
    'review': '👁️',
}


class ReviewActionView(ui.View):
    """Discord UI view with Approve/Deny buttons for mod review."""

    def __init__(self, pending_id: int, cog: 'AIModerationCog'):
        super().__init__(timeout=None)  # Persistent across restarts
        self.pending_id = pending_id
        self.cog = cog

    @ui.button(label='Approve', style=discord.ButtonStyle.danger, emoji='✅',
               custom_id='mod_review_approve')
    async def approve(self, interaction: discord.Interaction, button: ui.Button):
        """Approve the pending moderation action."""
        await self.cog._handle_review_decision(
            interaction, self.pending_id, 'approved',
        )

    @ui.button(label='Deny', style=discord.ButtonStyle.secondary, emoji='❌',
               custom_id='mod_review_deny')
    async def deny(self, interaction: discord.Interaction, button: ui.Button):
        """Deny the pending moderation action (no action taken)."""
        await self.cog._handle_review_decision(
            interaction, self.pending_id, 'denied',
        )

    @ui.button(label='Reduce to Timeout', style=discord.ButtonStyle.primary, emoji='⏰',
               custom_id='mod_review_timeout')
    async def reduce_timeout(self, interaction: discord.Interaction, button: ui.Button):
        """Reduce the action to a timeout instead."""
        await self.cog._handle_review_decision(
            interaction, self.pending_id, 'reduced_timeout',
        )


class AIModerationCog(commands.Cog):
    """AI-powered content moderation with human-in-the-loop escalation."""

    def __init__(self, bot):
        self.bot = bot

        # Configuration from env vars
        self.enabled = os.getenv('MOD_ENABLED', 'false').lower() in ('true', '1', 'yes')
        self.log_channel_id = int(os.getenv('MOD_LOG_CHANNEL_ID', '0') or '0')
        self.review_channel_id = int(os.getenv('MOD_REVIEW_CHANNEL_ID', '0') or '0')
        self.auto_delete = os.getenv('MOD_AUTO_DELETE', 'true').lower() in ('true', '1', 'yes')
        self.auto_timeout = os.getenv('MOD_AUTO_TIMEOUT', 'true').lower() in ('true', '1', 'yes')
        self.default_timeout_minutes = int(os.getenv('MOD_DEFAULT_TIMEOUT_MINUTES', '10') or '10')
        self.max_auto_timeout_minutes = int(os.getenv('MOD_MAX_AUTO_TIMEOUT_MINUTES', '60') or '60')
        self.ignored_channels = set(_get_env_list('MOD_IGNORED_CHANNELS'))
        self.ignored_roles = set(_get_env_list('MOD_IGNORED_ROLES'))
        self.min_confidence = float(os.getenv('MOD_MIN_CONFIDENCE', '0.7') or '0.7')
        self.scan_bots = os.getenv('MOD_SCAN_BOTS', 'false').lower() in ('true', '1', 'yes')

        # AI manager
        self.ai_manager = None
        self.db = None

        # Message context buffer (guild_id -> channel_id -> [messages])
        self._context_buffer = {}
        self._max_context = 5

        if not self.enabled:
            logger.info("AI Moderation: Disabled via MOD_ENABLED")
            return

        if not AI_SUPPORT:
            logger.warning("AI Moderation: AI module not available")
            self.enabled = False
            return

        try:
            self.ai_manager = get_ai_manager()
            if not self.ai_manager.is_feature_enabled('moderation'):
                logger.warning("AI Moderation: Moderation feature not enabled in AI config")
                self.enabled = False
                return
            logger.info("AI Moderation: Initialized with AI-powered analysis")
        except Exception as e:
            logger.error(f"AI Moderation: Failed to initialize AI manager: {e}")
            self.enabled = False

    async def cog_load(self):
        """Initialize database when the cog loads."""
        if not self.enabled:
            return
        if DB_SUPPORT:
            try:
                self.db = await get_database()
                logger.info("AI Moderation: Database connected for offender tracking")
            except Exception as e:
                logger.error(f"AI Moderation: Database init failed: {e}")

    def _should_moderate(self, message: discord.Message) -> bool:
        """Check if a message should be moderated."""
        if not self.enabled:
            return False
        if message.author.bot and not self.scan_bots:
            return False
        if not message.guild:
            return False
        if str(message.channel.id) in self.ignored_channels:
            return False
        # Check for ignored roles
        if hasattr(message.author, 'roles'):
            for role in message.author.roles:
                if str(role.id) in self.ignored_roles:
                    return False
        # Don't moderate the bot itself
        if message.author.id == self.bot.user.id:
            return False
        # Skip empty messages (images/embeds only)
        if not message.content or not message.content.strip():
            return False
        return True

    def _buffer_context(self, message: discord.Message):
        """Buffer recent messages for context-aware moderation."""
        guild_id = str(message.guild.id)
        channel_id = str(message.channel.id)

        if guild_id not in self._context_buffer:
            self._context_buffer[guild_id] = {}
        if channel_id not in self._context_buffer[guild_id]:
            self._context_buffer[guild_id][channel_id] = []

        buf = self._context_buffer[guild_id][channel_id]
        buf.append(f"{message.author.name}: {message.content[:200]}")
        if len(buf) > self._max_context:
            buf.pop(0)

    def _get_context(self, message: discord.Message) -> List[str]:
        """Get recent message context for a channel."""
        guild_id = str(message.guild.id)
        channel_id = str(message.channel.id)
        return self._context_buffer.get(guild_id, {}).get(channel_id, [])

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Analyze every message for content violations."""
        if not self._should_moderate(message):
            return

        # Buffer context first
        self._buffer_context(message)

        # Get infraction count for repeat-offender awareness
        infraction_count = 0
        if self.db:
            try:
                infraction_count = await self.db.get_user_infraction_count(
                    str(message.guild.id), str(message.author.id),
                )
            except Exception as e:
                logger.debug(f"Could not fetch infraction count: {e}")

        # Run AI analysis
        try:
            result = await self.ai_manager.moderation.analyze(
                message_content=message.content,
                username=message.author.name,
                channel_name=getattr(message.channel, 'name', ''),
                context_messages=self._get_context(message),
                infraction_count=infraction_count,
                default_timeout_minutes=self.default_timeout_minutes,
            )
        except Exception as e:
            logger.error(f"AI Moderation analysis error: {e}")
            return

        if result is None or result.is_safe:
            return

        # Below minimum confidence — skip
        if result.confidence < self.min_confidence:
            logger.debug(
                f"Moderation below confidence threshold ({result.confidence:.2f} < {self.min_confidence}): "
                f"{result.category.value} for {message.author.name}"
            )
            return

        # Determine if this needs human review
        needs_review = self.ai_manager.moderation.needs_human_review(result)

        if needs_review:
            await self._escalate_to_review(message, result, infraction_count)
        else:
            await self._execute_auto_action(message, result, infraction_count)

    async def _execute_auto_action(
        self,
        message: discord.Message,
        result: ModerationResult,
        infraction_count: int,
    ):
        """Execute an automatic moderation action."""
        action = result.suggested_action
        guild = message.guild
        member = message.author

        # Record infraction in database
        if self.db:
            try:
                await self.db.add_infraction(
                    guild_id=str(guild.id),
                    user_id=str(member.id),
                    username=member.name,
                    category=result.category.value,
                    reason=result.reason,
                    action=action,
                    confidence=result.confidence,
                    actor='bot',
                    actor_id=str(self.bot.user.id),
                    message_content=message.content[:500],
                    channel_id=str(message.channel.id),
                    channel_name=getattr(message.channel, 'name', ''),
                    message_id=str(message.id),
                )
            except Exception as e:
                logger.error(f"Failed to record infraction: {e}")

        # Execute the action
        try:
            if action == 'warn':
                await self._action_warn(message, result)
            elif action == 'delete':
                await self._action_delete(message, result)
            elif action in ('mute', 'timeout'):
                await self._action_timeout(message, result)
            else:
                logger.debug(f"No auto-action for '{action}'")
        except Exception as e:
            logger.error(f"Failed to execute moderation action '{action}': {e}")

        # Log to mod channel
        await self._log_action(message, result, auto=True)

    async def _action_warn(self, message: discord.Message, result: ModerationResult):
        """Send a warning to the user."""
        emoji = CATEGORY_EMOJI.get(result.category.value, '⚠️')
        try:
            await message.reply(
                f"{emoji} **Warning:** {result.reason}\n"
                f"-# *This is an automated moderation notice.*",
                delete_after=30,
            )
        except discord.Forbidden:
            logger.warning(f"Cannot send warning in {message.channel}")

    async def _action_delete(self, message: discord.Message, result: ModerationResult):
        """Delete the offending message and optionally warn."""
        if self.auto_delete:
            try:
                await message.delete()
            except discord.Forbidden:
                logger.warning(f"Cannot delete message in {message.channel}")
                return
            except discord.NotFound:
                pass  # Already deleted

            # Send notice
            emoji = CATEGORY_EMOJI.get(result.category.value, '🗑️')
            try:
                notice = await message.channel.send(
                    f"{emoji} A message from {message.author.mention} was removed: {result.reason}\n"
                    f"-# *Automated moderation action.*",
                )
                await notice.delete(delay=15)
            except discord.Forbidden:
                pass

    async def _action_timeout(self, message: discord.Message, result: ModerationResult):
        """Timeout the user."""
        if not self.auto_timeout:
            return

        member = message.author
        if not isinstance(member, discord.Member):
            return

        # Calculate timeout duration (escalate for repeat offenders)
        duration_minutes = self.default_timeout_minutes
        if self.db:
            count = await self.db.get_user_infraction_count(
                str(message.guild.id), str(member.id),
            )
            if count >= 3:
                duration_minutes = min(duration_minutes * 2, self.max_auto_timeout_minutes)
            if count >= 5:
                duration_minutes = min(duration_minutes * 4, self.max_auto_timeout_minutes)

        # Cap at max auto timeout
        if duration_minutes > self.max_auto_timeout_minutes:
            # Needs human review for longer timeouts
            await self._escalate_to_review(message, result, count if self.db else 0)
            return

        try:
            await member.timeout(
                timedelta(minutes=duration_minutes),
                reason=f"AI Moderation: {result.category.value} - {result.reason}",
            )
        except discord.Forbidden:
            logger.warning(f"Cannot timeout {member.name} — insufficient permissions")
            return

        # Delete the message too
        if self.auto_delete:
            try:
                await message.delete()
            except (discord.Forbidden, discord.NotFound):
                pass

        # Notify
        try:
            await message.channel.send(
                f"⏰ {member.mention} has been timed out for {duration_minutes} minutes: "
                f"{result.reason}\n-# *Automated moderation action.*",
                delete_after=30,
            )
        except discord.Forbidden:
            pass

    async def _escalate_to_review(
        self,
        message: discord.Message,
        result: ModerationResult,
        infraction_count: int,
    ):
        """Send the action to the mod review channel for human approval."""
        review_channel = None
        if self.review_channel_id:
            review_channel = self.bot.get_channel(self.review_channel_id)

        if not review_channel:
            # Fall back to log channel
            if self.log_channel_id:
                review_channel = self.bot.get_channel(self.log_channel_id)

        if not review_channel:
            logger.warning("No review channel configured — cannot escalate moderation action")
            # Still delete if it's doxxing (safety override)
            if result.category == ModerationCategory.DOXXING and self.auto_delete:
                try:
                    await message.delete()
                except (discord.Forbidden, discord.NotFound):
                    pass
            return

        # Store the pending action in the database
        pending_id = None
        if self.db:
            try:
                pending_id = await self.db.add_pending_action(
                    guild_id=str(message.guild.id),
                    user_id=str(message.author.id),
                    username=message.author.name,
                    action=result.suggested_action,
                    reason=result.reason,
                    category=result.category.value,
                    confidence=result.confidence,
                    message_content=message.content[:500],
                    channel_id=str(message.channel.id),
                    message_id=str(message.id),
                )
            except Exception as e:
                logger.error(f"Failed to store pending action: {e}")

        # Build review embed
        cat_emoji = CATEGORY_EMOJI.get(result.category.value, '❓')
        act_emoji = ACTION_EMOJI.get(result.suggested_action, '❓')
        color = CATEGORY_COLORS.get(result.category.value, 0x7F8C8D)

        embed = discord.Embed(
            title=f"{cat_emoji} Moderation Review Required",
            description=(
                f"**AI recommends:** {act_emoji} **{result.suggested_action.upper()}**\n"
                f"**Category:** {result.category.value}\n"
                f"**Confidence:** {result.confidence:.0%}\n"
                f"**Reason:** {result.reason}"
            ),
            color=color,
            timestamp=datetime.now(timezone.utc),
        )

        embed.add_field(
            name="👤 User",
            value=f"{message.author.mention} (`{message.author.name}`)\nID: `{message.author.id}`",
            inline=True,
        )
        embed.add_field(
            name="📍 Channel",
            value=f"<#{message.channel.id}>",
            inline=True,
        )
        embed.add_field(
            name="📊 Prior Infractions",
            value=str(infraction_count),
            inline=True,
        )

        # Truncate message content for the embed
        content_preview = message.content[:500]
        if len(message.content) > 500:
            content_preview += '...'
        embed.add_field(
            name="💬 Message Content",
            value=f"```\n{content_preview}\n```",
            inline=False,
        )

        if result.pii_detected:
            embed.add_field(
                name="🔐 PII Detected",
                value=', '.join(result.pii_detected),
                inline=False,
            )

        if pending_id:
            embed.set_footer(text=f"Pending Action ID: {pending_id}")

        # Send with review buttons
        view = ReviewActionView(pending_id or 0, self) if pending_id else None
        try:
            review_msg = await review_channel.send(embed=embed, view=view)

            # Update pending action with review message ID
            if pending_id and self.db:
                await self.db._execute(
                    "UPDATE mod_pending_actions SET review_message_id = ? WHERE id = ?",
                    (str(review_msg.id), pending_id),
                )
        except discord.Forbidden:
            logger.error(f"Cannot send review message to channel {review_channel}")

        # For doxxing: auto-delete even while pending review (safety override)
        if result.category == ModerationCategory.DOXXING and self.auto_delete:
            try:
                await message.delete()
                logger.info(f"Auto-deleted doxxing content from {message.author.name} pending review")
            except (discord.Forbidden, discord.NotFound):
                pass

    async def _handle_review_decision(
        self,
        interaction: discord.Interaction,
        pending_id: int,
        decision: str,
    ):
        """Handle a moderator's decision on a pending action."""
        if not self.db:
            await interaction.response.send_message(
                "❌ Database unavailable — cannot process review.", ephemeral=True,
            )
            return

        pending = await self.db.get_pending_action(pending_id)
        if not pending:
            await interaction.response.send_message(
                "❌ Pending action not found.", ephemeral=True,
            )
            return

        if pending['status'] != 'pending':
            await interaction.response.send_message(
                f"This action was already **{pending['status']}** by {pending.get('reviewer_name', 'unknown')}.",
                ephemeral=True,
            )
            return

        guild = interaction.guild
        if not guild:
            return

        reviewer = interaction.user

        if decision == 'approved':
            # Execute the original action
            action = pending['action']
            user_id = int(pending['user_id'])
            member = guild.get_member(user_id)

            if not member:
                try:
                    member = await guild.fetch_member(user_id)
                except discord.NotFound:
                    await interaction.response.send_message(
                        "❌ User no longer in the server.", ephemeral=True,
                    )
                    return

            reason = f"Approved by {reviewer.name}: {pending['reason']}"

            try:
                if action == 'kick':
                    await member.kick(reason=reason)
                elif action == 'ban':
                    await member.ban(reason=reason, delete_message_days=1)
                else:
                    # Fallback: timeout
                    await member.timeout(
                        timedelta(minutes=self.default_timeout_minutes),
                        reason=reason,
                    )
            except discord.Forbidden:
                await interaction.response.send_message(
                    f"❌ Insufficient permissions to **{action}** {member.mention}.",
                    ephemeral=True,
                )
                return

            # Record the infraction (with human actor)
            await self.db.add_infraction(
                guild_id=str(guild.id),
                user_id=str(user_id),
                username=pending['username'],
                category=pending['category'],
                reason=pending['reason'],
                action=action,
                confidence=pending['confidence'],
                actor=reviewer.name,
                actor_id=str(reviewer.id),
                message_content=pending.get('message_content', ''),
                channel_id=pending.get('channel_id', ''),
                message_id=pending.get('message_id', ''),
            )

            await self.db.resolve_pending_action(
                pending_id, 'approved', str(reviewer.id), reviewer.name,
            )

            await interaction.response.send_message(
                f"✅ **{action.upper()}** approved by {reviewer.mention} for <@{user_id}>.",
            )

        elif decision == 'denied':
            await self.db.resolve_pending_action(
                pending_id, 'denied', str(reviewer.id), reviewer.name,
            )
            await interaction.response.send_message(
                f"❌ Action **denied** by {reviewer.mention}. No action taken.",
            )

        elif decision == 'reduced_timeout':
            user_id = int(pending['user_id'])
            member = guild.get_member(user_id)
            if member:
                try:
                    await member.timeout(
                        timedelta(minutes=self.default_timeout_minutes),
                        reason=f"Reduced from {pending['action']} by {reviewer.name}",
                    )
                except discord.Forbidden:
                    await interaction.response.send_message(
                        f"❌ Cannot timeout {member.mention}.", ephemeral=True,
                    )
                    return

            # Record reduced action
            await self.db.add_infraction(
                guild_id=str(guild.id),
                user_id=str(user_id),
                username=pending['username'],
                category=pending['category'],
                reason=f"Reduced from {pending['action']}: {pending['reason']}",
                action='timeout',
                confidence=pending['confidence'],
                actor=reviewer.name,
                actor_id=str(reviewer.id),
                message_content=pending.get('message_content', ''),
                channel_id=pending.get('channel_id', ''),
                message_id=pending.get('message_id', ''),
            )

            await self.db.resolve_pending_action(
                pending_id, 'reduced_timeout', str(reviewer.id), reviewer.name,
            )

            await interaction.response.send_message(
                f"⏰ Action reduced to **timeout** ({self.default_timeout_minutes}m) by {reviewer.mention}.",
            )

        # Disable the buttons on the review message
        try:
            await interaction.message.edit(view=None)
        except Exception:
            pass

    async def _log_action(
        self,
        message: discord.Message,
        result: ModerationResult,
        auto: bool = True,
    ):
        """Log a moderation action to the log channel."""
        if not self.log_channel_id:
            return

        log_channel = self.bot.get_channel(self.log_channel_id)
        if not log_channel:
            return

        cat_emoji = CATEGORY_EMOJI.get(result.category.value, '❓')
        act_emoji = ACTION_EMOJI.get(result.suggested_action, '❓')
        color = CATEGORY_COLORS.get(result.category.value, 0x7F8C8D)

        embed = discord.Embed(
            title=f"{cat_emoji} {'Auto' if auto else 'Manual'} Moderation Action",
            color=color,
            timestamp=datetime.now(timezone.utc),
        )

        embed.add_field(name="User", value=f"{message.author.mention}", inline=True)
        embed.add_field(name="Action", value=f"{act_emoji} {result.suggested_action}", inline=True)
        embed.add_field(name="Category", value=result.category.value, inline=True)
        embed.add_field(name="Confidence", value=f"{result.confidence:.0%}", inline=True)
        embed.add_field(name="Channel", value=f"<#{message.channel.id}>", inline=True)
        embed.add_field(name="Reason", value=result.reason[:200], inline=False)

        if result.pii_detected:
            embed.add_field(name="PII Detected", value=', '.join(result.pii_detected), inline=False)

        try:
            await log_channel.send(embed=embed)
        except discord.Forbidden:
            logger.warning(f"Cannot send to mod log channel {self.log_channel_id}")

    # ── Mod Commands ──────────────────────────────────────────────────────

    @commands.hybrid_command(name='mod_history', description='View moderation history for a user')
    @commands.has_permissions(manage_messages=True)
    async def mod_history(self, ctx: commands.Context, member: discord.Member):
        """View a user's moderation infraction history."""
        if not self.db:
            await ctx.send("❌ Database not available.", ephemeral=True)
            return

        infractions = await self.db.get_user_infractions(
            str(ctx.guild.id), str(member.id), limit=15,
        )

        if not infractions:
            await ctx.send(f"✅ {member.mention} has no recorded infractions.", ephemeral=True)
            return

        embed = discord.Embed(
            title=f"📋 Moderation History: {member.name}",
            color=0xE74C3C,
            timestamp=datetime.now(timezone.utc),
        )

        total = await self.db.get_user_infraction_count(str(ctx.guild.id), str(member.id))
        embed.description = f"**Total infractions:** {total}\nShowing most recent {len(infractions)}:"

        for inf in infractions[:10]:
            cat_emoji = CATEGORY_EMOJI.get(inf['category'], '❓')
            act_emoji = ACTION_EMOJI.get(inf['action'], '❓')
            ts = inf['created_at'][:16].replace('T', ' ')
            resolved = ' ✅' if inf.get('resolved') else ''

            embed.add_field(
                name=f"{cat_emoji} #{inf['id']} — {ts}{resolved}",
                value=(
                    f"{act_emoji} **{inf['action']}** | {inf['category']}\n"
                    f"Reason: {inf['reason'][:100]}\n"
                    f"By: {inf['actor']}"
                ),
                inline=False,
            )

        await ctx.send(embed=embed, ephemeral=True)

    @commands.hybrid_command(name='mod_recent', description='Show recent moderation actions')
    @commands.has_permissions(manage_messages=True)
    async def mod_recent(self, ctx: commands.Context):
        """Show recent moderation actions in this server."""
        if not self.db:
            await ctx.send("❌ Database not available.", ephemeral=True)
            return

        infractions = await self.db.get_recent_infractions(str(ctx.guild.id), limit=15)

        if not infractions:
            await ctx.send("✅ No moderation actions recorded yet.", ephemeral=True)
            return

        embed = discord.Embed(
            title="📋 Recent Moderation Actions",
            color=0x3498DB,
            timestamp=datetime.now(timezone.utc),
        )

        for inf in infractions[:10]:
            cat_emoji = CATEGORY_EMOJI.get(inf['category'], '❓')
            act_emoji = ACTION_EMOJI.get(inf['action'], '❓')
            ts = inf['created_at'][:16].replace('T', ' ')

            embed.add_field(
                name=f"{cat_emoji} #{inf['id']} — {ts}",
                value=(
                    f"**User:** {inf['username']} | {act_emoji} **{inf['action']}**\n"
                    f"Reason: {inf['reason'][:100]}\n"
                    f"By: {inf['actor']}"
                ),
                inline=False,
            )

        await ctx.send(embed=embed, ephemeral=True)

    @commands.hybrid_command(name='mod_pending', description='Show pending moderation reviews')
    @commands.has_permissions(manage_messages=True)
    async def mod_pending(self, ctx: commands.Context):
        """Show actions waiting for moderator review."""
        if not self.db:
            await ctx.send("❌ Database not available.", ephemeral=True)
            return

        pending = await self.db.get_pending_actions(str(ctx.guild.id))

        if not pending:
            await ctx.send("✅ No pending moderation reviews.", ephemeral=True)
            return

        embed = discord.Embed(
            title=f"⏳ Pending Moderation Reviews ({len(pending)})",
            color=0xF39C12,
            timestamp=datetime.now(timezone.utc),
        )

        for p in pending[:10]:
            cat_emoji = CATEGORY_EMOJI.get(p['category'], '❓')
            act_emoji = ACTION_EMOJI.get(p['action'], '❓')
            ts = p['created_at'][:16].replace('T', ' ')

            embed.add_field(
                name=f"{cat_emoji} #{p['id']} — {ts}",
                value=(
                    f"**User:** {p['username']} | {act_emoji} **{p['action']}**\n"
                    f"Confidence: {p['confidence']:.0%} | {p['reason'][:80]}"
                ),
                inline=False,
            )

        await ctx.send(embed=embed, ephemeral=True)

    @commands.hybrid_command(name='mod_resolve', description='Resolve/dismiss an infraction')
    @commands.has_permissions(manage_messages=True)
    async def mod_resolve(self, ctx: commands.Context, infraction_id: int, *, notes: str = ''):
        """Mark an infraction as resolved with optional notes."""
        if not self.db:
            await ctx.send("❌ Database not available.", ephemeral=True)
            return

        await self.db.resolve_infraction(infraction_id, notes=notes)
        await ctx.send(f"✅ Infraction #{infraction_id} resolved.", ephemeral=True)


async def setup(bot):
    """Load the AI Moderation cog."""
    await bot.add_cog(AIModerationCog(bot))
    logger.info("AIModerationCog loaded")
