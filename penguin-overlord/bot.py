# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
Penguin Overlord - A fun Discord bot with various features.
Main bot entry point.
"""

import sys
from pathlib import Path
import discord
from discord.ext import commands
from dotenv import load_dotenv

from utils.config import Config, ConfigError, describe_config, load_config
from utils.logging_setup import configure_logging, describe_logging

# Load environment variables (fallback if not using secrets manager).
# Before logging is configured, so a LOG_LEVEL in .env is honoured.
load_dotenv()

logger = configure_logging('bot')

class PenguinOverlord(commands.Bot):
    """The Penguin Overlord Discord bot."""

    def __init__(self, config: Config = None):
        intents = discord.Intents.default()
        intents.message_content = True
        # Server Members Intent: without it Discord never delivers
        # on_member_update / on_member_join, so the welcome greeter's
        # role-grant detection is silent. Privileged — must ALSO be enabled
        # in the Developer Portal (Application → Bot → Server Members Intent).
        intents.members = True

        # Validated once in main(); None only in tests that build the bot
        # without an environment. Cogs still read the environment themselves
        # until they migrate to `self.bot.config`.
        self.config = config

        super().__init__(
            command_prefix='!',
            intents=intents,
            description='Penguin Overlord - Your fun companion bot!',
            owner_id=config.discord.owner_id if config else None
        )

        # Completely disable the default help command
        self.help_command = None
    
    async def setup_hook(self):
        """Load extensions/cogs when bot starts."""
        logger.info("Loading extensions...")

        # Load all cogs from the cogs directory
        loaded, failed = [], []
        cogs_path = Path(__file__).parent / 'cogs'
        if cogs_path.exists():
            for file in cogs_path.glob('*.py'):
                if file.name.startswith('_'):
                    continue

                try:
                    await self.load_extension(f'cogs.{file.stem}')
                    loaded.append(file.stem)
                    logger.info(f"✓ Loaded extension: {file.stem}")
                except Exception as e:
                    failed.append(file.stem)
                    # exc_info: a bare message hid which import actually broke
                    logger.error(f"✗ Failed to load extension {file.stem}: {e}", exc_info=e)
        logger.info('Extensions: %d loaded, %d failed%s', len(loaded), len(failed),
                    f" ({', '.join(failed)})" if failed else '')

    async def on_ready(self):
        """Called when the bot is ready."""
        logger.info(f'🐧 {self.user} has connected to Discord!')
        logger.info(f'Bot is in {len(self.guilds)} guild(s)')
        
        # Sync slash commands with Discord
        try:
            synced = await self.tree.sync()
            logger.info(f"✓ Synced {len(synced)} slash command(s)")
        except Exception as e:
            logger.error(f"✗ Failed to sync commands: {e}")
        
        # Set bot status
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name="for !help | 🐧"
            )
        )
    
    async def on_command_error(self, ctx, error):
        """Handle command errors."""
        if isinstance(error, commands.CommandNotFound):
            return
        
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(f'❌ Missing required argument: {error.param}')
            return
        
        if isinstance(error, commands.BadArgument):
            await ctx.send(f'❌ Bad argument: {error}')
            return
        
        # Log unexpected errors
        logger.error(f'Unexpected error in {ctx.command}: {error}', exc_info=error)
        await ctx.send('❌ An unexpected error occurred. Please try again later.')


def main():
    """Main entry point for the bot."""
    # One pass over the environment (secrets manager first, then .env):
    # every missing or malformed variable is reported together, and the
    # process exits non-zero so a container restart loop is visible.
    try:
        config = load_config()
    except ConfigError as e:
        logger.error("❌ Refusing to start:\n%s", e)
        logger.error("See .env.example and docs/reference/CONFIGURATION.md; "
                     "`python scripts/check-config.py` re-runs this check.")
        sys.exit(1)

    logger.info('Penguin Overlord starting — logging %s', describe_logging())
    logger.info('Config: %s', describe_config(config))

    bot = PenguinOverlord(config)

    try:
        # log_handler=None: discord.py otherwise installs its own root
        # handler alongside ours and every discord.* record is logged twice.
        bot.run(config.discord.bot_token.reveal(), log_handler=None)
    except discord.LoginFailure:
        logger.error("❌ Invalid Discord bot token!")
    except Exception as e:
        logger.error(f"❌ Failed to start bot: {e}", exc_info=e)


if __name__ == '__main__':
    main()
