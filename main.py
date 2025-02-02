import nextcord
import asyncio
from nextcord import Interaction, ButtonStyle, PermissionOverwrite, SlashOption
from nextcord.ui import Button, View, Modal, TextInput
from nextcord.ext import commands
from enum import Enum
from typing import Optional
import requests  # Add at the top with other imports
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading

load_dotenv()

intents = nextcord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

ticket_cooldowns = {}
COOLDOWN_DURATION = timedelta(hours=24)

# Configure these with your IDs
EVAL_CATEGORY_ID = 1301209739132407879  # Regular evaluation category
HT3_CATEGORY_ID = 1301209771843780670  # HT3+ category
STAFF_ROLE_ID = 1327443019212914728  # Staff role
RESULTS_CHANNEL_ID = 1290032240197242880  # Results channel

MINIMUM_COMMAND_ROLE_ID = 1327443019212914728

# Role IDs for each tier
TIER_ROLES = {
    "Low Tier 1": 1290065742850424894,
    "High Tier 1": 1290065773502402643,
    "Low Tier 2": 1290065700366319709,
    "High Tier 2": 1290065725473685546,
    "Low Tier 3": 1290065653377794100,
    "High Tier 3": 1290065680883912807,
    "Low Tier 4": 1290065596729393226,
    "High Tier 4": 1290065632020402311,
    "Low Tier 5": 1290065509173170207,
    "High Tier 5": 1290065563514703883,
}

def has_required_role(interaction: Interaction) -> bool:
    required_role = interaction.guild.get_role(MINIMUM_COMMAND_ROLE_ID)
    if not required_role:
        return False
    return required_role in interaction.user.roles

def require_role():
    async def predicate(interaction: Interaction):
        if not has_required_role(interaction):
            await interaction.response.send_message(
                "You don't have permission to use this command.",
                ephemeral=True
            )
            return False
        return True
    return predicate

class TestType(Enum):
    EVALUATION = "evaluation"
    HT3_PLUS = "ht3plus"


class TestingForm(Modal):
    def __init__(self, test_type: TestType):
        super().__init__(title="Testing Application")
        self.test_type = test_type

        self.ign = TextInput(
            label="Minecraft Username",
            placeholder="Enter your Minecraft username",
            required=True,
        )
        self.add_item(self.ign)

        self.server = TextInput(
            label="Preferred Server",
            placeholder="Enter your preferred server",
            required=True,
        )
        self.add_item(self.server)

        self.region = TextInput(
            label="Region",
            placeholder="NA/EU/AS/ME",
            required=True,
        )
        self.add_item(self.region)

        # Conditional label based on test type
        tier_label = "Goal Tier" if self.test_type == TestType.HT3_PLUS else "Current Tier"
        self.tier = TextInput(
            label=tier_label,
            placeholder="Enter your tier",
            required=True,
        )
        self.add_item(self.tier)

    async def callback(self, interaction: Interaction):
        try:
            await interaction.response.defer(ephemeral=True)
            
            user_id = interaction.user.id
            if user_id in ticket_cooldowns:
                time_remaining = ticket_cooldowns[user_id] - datetime.now()
                if time_remaining.total_seconds() > 0:
                    hours = int(time_remaining.total_seconds() // 3600)
                    minutes = int((time_remaining.total_seconds() % 3600) // 60)
                    await interaction.followup.send(
                        f"You must wait {hours}h {minutes}m before creating another ticket.",
                        ephemeral=True
                    )
                    return

            category_id = HT3_CATEGORY_ID if self.test_type == TestType.HT3_PLUS else EVAL_CATEGORY_ID
            category = interaction.guild.get_channel(category_id)
            staff_role = interaction.guild.get_role(STAFF_ROLE_ID)

            if not category or not staff_role:
                await interaction.followup.send(
                    "Error: Category or Staff role not found! Please contact an administrator.",
                    ephemeral=True
                )
                return

            overwrites = {
                interaction.guild.default_role: PermissionOverwrite(read_messages=False),
                interaction.guild.me: PermissionOverwrite(read_messages=True, send_messages=True),
                interaction.user: PermissionOverwrite(read_messages=True, send_messages=True),
                staff_role: PermissionOverwrite(read_messages=True, send_messages=True)
            }

            channel_name = f"ticket-{interaction.user.id}-{self.ign.value}"
            channel_name = channel_name.lower().replace(' ', '-')

            try:
                ticket_channel = await interaction.guild.create_text_channel(
                    name=channel_name,
                    category=category,
                    overwrites=overwrites,
                    topic=f"Tier Testing Ticket for {interaction.user.mention}"
                )

                ticket_cooldowns[interaction.user.id] = datetime.now() + COOLDOWN_DURATION

                embed = nextcord.Embed(
                    title="New Testing Application",
                    description="A staff member will be with you shortly.",
                    color=0x00ff00
                )
                embed.add_field(name="Applicant", value=interaction.user.mention, inline=False)
                embed.add_field(name="Minecraft Username", value=self.ign.value, inline=False)
                embed.add_field(name="Preferred Server", value=self.server.value, inline=False)
                embed.add_field(name="Region", value=self.region.value, inline=False)
                # Update the message for HT3+ testing
                if self.test_type == TestType.HT3_PLUS:
                    embed.add_field(name="Goal Tier", value=self.tier.value, inline=False)
                else:
                    embed.add_field(name="Current Tier", value=self.tier.value, inline=False)
                embed.add_field(name="Test Type",
                                value="HT3+ Testing" if self.test_type == TestType.HT3_PLUS else "Evaluation", inline=False)
                await ticket_channel.send(f"{staff_role.mention} New tier testing ticket!", embed=embed)
                await interaction.followup.send(
                    f"Ticket created successfully! Please check {ticket_channel.mention}",
                    ephemeral=True
                )

            except Exception as e:
                await interaction.followup.send(
                    f"An error occurred: {str(e)}",
                    ephemeral=True
                )

        except nextcord.errors.InteractionResponded:
            try:
                await interaction.followup.send(
                    "Processing your request...",
                    ephemeral=True
                )
            except:
                pass
        except Exception as e:
            try:
                await interaction.followup.send(
                    f"An error occurred: {str(e)}",
                    ephemeral=True
                )
            except:
                print(f"Error in callback: {str(e)}")


class TestingView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @nextcord.ui.button(label="Evaluation Testing", style=ButtonStyle.primary)
    async def eval_button(self, button: Button, interaction: Interaction):
        testing_form = TestingForm(TestType.EVALUATION)
        await interaction.response.send_modal(testing_form)

    @nextcord.ui.button(label="HT3+ Testing", style=ButtonStyle.danger)
    async def ht3_button(self, button: Button, interaction: Interaction):
        testing_form = TestingForm(TestType.HT3_PLUS)
        await interaction.response.send_modal(testing_form)


# Add these constants near other configuration
VALID_REGIONS = ["NA", "EU", "AS", "ME"]
VALID_RANKS = [
    "Unranked",
    "Low Tier 1", "High Tier 1",
    "Low Tier 2", "High Tier 2",
    "Low Tier 3", "High Tier 3",
    "Low Tier 4", "High Tier 4",
    "Low Tier 5", "High Tier 5"
]

# Helper function to get Minecraft UUID
async def get_minecraft_uuid(username: str) -> str:
    try:
        url = f'https://api.mojang.com/users/profiles/minecraft/{username}'
        print(f"Fetching UUID for username: {username}")
        response = requests.get(url)
        if response.status_code == 200:
            uuid = response.json()['id']
            print(f"Found UUID: {uuid}")
            return uuid
        print(f"Failed to get UUID. Status code: {response.status_code}")
        return None
    except Exception as e:
        print(f"Error getting UUID: {e}")
        return None

@bot.slash_command(name="results", description="Submit test results and close ticket")
async def results(
        interaction: Interaction,
        mc_username: str = SlashOption(description="Minecraft username of the player", required=True),
        region: str = SlashOption(
            description="Player's region",
            required=True,
            choices=VALID_REGIONS
        ),
        previous_rank: str = SlashOption(
            description="Previous rank of the player",
            required=True,
            choices=VALID_RANKS
        ),
        new_rank: str = SlashOption(
            description="New rank earned by the player",
            required=True,
            choices=VALID_RANKS
        )
):
    try:
        # Check role first
        if not has_required_role(interaction):
            try:
                await interaction.response.send_message(
                    "You don't have permission to use this command.",
                    ephemeral=True
                )
            except:
                await interaction.followup.send(
                    "You don't have permission to use this command.",
                    ephemeral=True
                )
            return

        try:
            await interaction.response.defer(ephemeral=True)
        except:
            pass
        
        print(f"\n=== Processing Results Command ===")
        print(f"Channel: {interaction.channel.name}")
        print(f"MC Username: {mc_username}")
        
        # Verify command is used in a ticket channel
        if not interaction.channel.name.startswith("ticket-"):
            await interaction.followup.send("This command can only be used in ticket channels!", ephemeral=True)
            return

        # Get the tested user from the ticket channel name
        tested_user = None
        channel_name_parts = interaction.channel.name.split('-')
        
        print(f"Channel name parts: {channel_name_parts}")
        
        if len(channel_name_parts) >= 2:
            try:
                user_id = int(channel_name_parts[1])
                print(f"Looking for user ID: {user_id}")
                tested_user = await interaction.guild.fetch_member(user_id)
                if tested_user:
                    print(f"Found matching user: {tested_user.name} (ID: {tested_user.id})")
            except (ValueError, nextcord.NotFound) as e:
                print(f"Error finding user: {e}")

        if not tested_user:
            await interaction.followup.send(
                f"Could not find the tested user! Channel format should be ticket-userid-minecraft",
                ephemeral=True
            )
            return

        minecraft_uuid = await get_minecraft_uuid(mc_username)
        if not minecraft_uuid:
            await interaction.response.send_message(
                f"Could not find Minecraft player: {mc_username}",
                ephemeral=True
            )
            return

        # Create results embed
        results_embed = nextcord.Embed(
            color=0xff0000
        )

        results_embed.set_author(
            name=f"{tested_user.display_name}'s Test Results 🏆",
            icon_url=tested_user.display_avatar.url
        )

        results_embed.add_field(name="Tester", value=interaction.user.mention, inline=False)
        results_embed.add_field(name="Player", value=tested_user.mention, inline=False)
        results_embed.add_field(name="Region", value=region, inline=False)
        results_embed.add_field(name="Minecraft Username", value=mc_username, inline=False)
        results_embed.add_field(name="Previous Rank", value=previous_rank, inline=False)
        results_embed.add_field(name="Rank Earned", value=new_rank, inline=False)

        print(f"Embed fields: {results_embed.to_dict()}")

        # Send results to results channel
        results_channel = interaction.guild.get_channel(RESULTS_CHANNEL_ID)
        if results_channel:
            try:
                message = await results_channel.send(content=tested_user.mention, embed=results_embed)
                emojis = ["👑", "🥳", "😱", "😭", "😂", "💀"]

                for emoji in emojis:
                    await message.add_reaction(emoji)
            except Exception as e:
                await interaction.followup.send(
                    f"Error sending results: {str(e)}",
                    ephemeral=True
                )
                return
        else:
            await interaction.followup.send(
                "Results channel not found!",
                ephemeral=True
            )
            return

        # Assign new role
        if new_rank in TIER_ROLES:
            try:
                # Remove old tier roles
                for role_name, role_id in TIER_ROLES.items():
                    role = interaction.guild.get_role(role_id)
                    if role and role in tested_user.roles:
                        await tested_user.remove_roles(role)

                # Add new tier role
                new_role = interaction.guild.get_role(TIER_ROLES[new_rank])
                if new_role:
                    await tested_user.add_roles(new_role)
                else:
                    await interaction.channel.send("Warning: Could not find the new rank role!")
            except Exception as e:
                await interaction.channel.send(f"Warning: Could not update roles: {str(e)}")

        # Notify about ticket closure
        await interaction.followup.send("Results submitted successfully!", ephemeral=True)
        await interaction.channel.send("Test completed! This ticket will be closed in 10 seconds.")

        # Delete the channel after 10 seconds
        await asyncio.sleep(10)
        await delete_channel(interaction.channel)

    except nextcord.errors.InteractionResponded:
        try:
            await interaction.followup.send("Processing your request...", ephemeral=True)
        except:
            pass
    except Exception as e:
        try:
            await interaction.followup.send(f"An error occurred: {str(e)}", ephemeral=True)
        except:
            print(f"Error in results command: {str(e)}")


@bot.slash_command(name="cooldown", description="Check your remaining ticket cooldown")
async def check_cooldown(interaction: Interaction):
    user_id = interaction.user.id
    if user_id not in ticket_cooldowns:
        await interaction.response.send_message("You have no active cooldown!", ephemeral=True)
        return

    time_remaining = ticket_cooldowns[user_id] - datetime.now()
    if time_remaining.total_seconds() <= 0:
        del ticket_cooldowns[user_id]
        await interaction.response.send_message("You have no active cooldown!", ephemeral=True)
    else:
        hours = int(time_remaining.total_seconds() // 3600)
        minutes = int((time_remaining.total_seconds() % 3600) // 60)
        await interaction.response.send_message(
            f"You must wait {hours}h {minutes}m before creating another ticket.",
            ephemeral=True
        )


@bot.event
async def on_ready():
    print("joho song is sped")
    print(f"Bot is ready! Logged in as {bot.user}")


@bot.event
async def on_disconnect():
    print("Bot disconnected! Attempting to reconnect...")


@bot.event
async def on_resumed():
    print("Bot reconnected!")


@bot.slash_command(name="setup123", description="Setup the testing system")
async def setup(interaction: Interaction):
    try:
        if not has_required_role(interaction):
            await interaction.response.send_message(
                "You don't have permission to use this command.",
                ephemeral=True
            )
            return

        embed = nextcord.Embed(title="Crystal Tier List", color=0x5865F2)
        embed.description = """Upon interacting, you will be asked to answer a form.
Once you have finished, a ticket will be created and await a Tester to respond.
If you are HT3 or higher, please use the HT3+ Testing button.
Once a tester has responded, your test will commence. Good Luck!

• Region should be the region of the server you wish to test on
• Username should be the name of the account you will be testing on"""

        view = TestingView()
        
        try:
            await interaction.response.send_message(embed=embed, view=view)
        except nextcord.errors.InteractionResponded:
            await interaction.followup.send(embed=embed, view=view)
            
    except Exception as e:
        print(f"Error in setup command: {str(e)}")
        try:
            await interaction.followup.send(
                "An error occurred while setting up the testing system.",
                ephemeral=True
            )
        except:
            pass


async def delete_channel(channel):
    try:
        await channel.delete()
    except nextcord.NotFound:
        print(f"Channel {channel.name} not found for deletion.")
    except Exception as e:
        print(f"Error deleting channel: {e}")


class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'OK')

def run_http_server():
    port = int(os.getenv('PORT', '8080'))
    server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
    server.serve_forever()

if __name__ == "__main__":
    # Start HTTP server in a separate thread
    threading.Thread(target=run_http_server, daemon=True).start()
    print("HTTP server started for health checks.")

    # Run the bot
    bot.run(os.getenv('DISCORD_TOKEN'))



