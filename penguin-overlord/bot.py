# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
Penguin Overlord - A fun Discord bot with various features.
Main bot entry point.
"""

import os
import logging
from pathlib import Path
import discord
from discord.ext import commands
from dotenv import load_dotenv

# Import secrets management
from utils.secrets import get_secret

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment variables (fallback if not using secrets manager)
load_dotenv()

class PenguinOverlord(commands.Bot):
    """The Penguin Overlord Discord bot."""
    
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        
        # Get owner ID from environment or secrets
        owner_id = get_secret('DISCORD', 'OWNER_ID')
        if not owner_id:
            owner_id = os.getenv('DISCORD_OWNER_ID')
        
        # Parse owner_id, handling placeholder values gracefully
        parsed_owner_id = None
        if owner_id and owner_id.isdigit():
            parsed_owner_id = int(owner_id)
        elif owner_id and not owner_id.startswith('your_'):
            # Log warning if invalid but not a placeholder
            print(f"⚠️  Warning: DISCORD_OWNER_ID '{owner_id}' is not a valid Discord user ID")
        
        super().__init__(
            command_prefix='!',
            intents=intents,
            description='Penguin Overlord - Your fun companion bot!',
            owner_id=parsed_owner_id
        )
        
        # Completely disable the default help command
        self.help_command = None
    
    async def setup_hook(self):
        """Load extensions/cogs when bot starts."""
        logger.info("Loading extensions...")
        
        # Load all cogs from the cogs directory
        cogs_path = Path(__file__).parent / 'cogs'
        if cogs_path.exists():
            for file in cogs_path.glob('*.py'):
                if file.name.startswith('_'):
                    continue
                
                try:
                    await self.load_extension(f'cogs.{file.stem}')
                    logger.info(f"✓ Loaded extension: {file.stem}")
                except Exception as e:
                    logger.error(f"✗ Failed to load extension {file.stem}: {e}")
    
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
    # Try to get token from secrets manager first, then fall back to env var
    token = get_secret('DISCORD', 'BOT_TOKEN')
    
    # If not in secrets manager, try direct env var
    if not token:
        token = os.getenv('DISCORD_BOT_TOKEN')
    
    if not token:
        logger.error("❌ DISCORD_BOT_TOKEN not found!")
        logger.error("You can set it via:")
        logger.error("  1. Doppler: Set DOPPLER_TOKEN env var and add DISCORD_BOT_TOKEN to your Doppler project")
        logger.error("  2. AWS Secrets Manager: Set SECRETS_MANAGER=aws and configure AWS credentials")
        logger.error("  3. HashiCorp Vault: Set SECRETS_MANAGER=vault and configure Vault credentials")
        logger.error("  4. .env file: Create .env with DISCORD_BOT_TOKEN=your_token")
        logger.error("See .env.example for reference.")
        return
    
    bot = PenguinOverlord()
    
    try:
        bot.run(token)
    except discord.LoginFailure:
        logger.error("❌ Invalid Discord bot token!")
    except Exception as e:
        logger.error(f"❌ Failed to start bot: {e}", exc_info=e)


if __name__ == '__main__':
    main()
