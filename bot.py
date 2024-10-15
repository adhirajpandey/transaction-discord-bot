import requests
import discord
from discord.ext import commands
import json
import asyncio
import os
from dotenv import load_dotenv

load_dotenv()

DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
DISCORD_CHANNEL_ID = int(os.getenv("DISCORD_CHANNEL_ID"))

AUTH_TOKEN = os.getenv("AUTH_TOKEN")

ADD_TRANSACTION_WEBHOOK_URL = os.getenv("ADD_TRANSACTION_WEBHOOK_URL")
EDGE_CACHE_URL = os.getenv("EDGE_CACHE_URL")

SLEEP_TIME_IN_MINUTES = int(os.getenv("SLEEP_TIME_IN_MINUTES"))




FOOD_SUBCATEGORIES = ["Breakfast", "Lunch", "Dinner", "Snacks"]
TRANSPORT_SUBCATEGORIES = ["Cab", "Auto", "Bike", "Others"]
SHOPPING_SUBCATEGORIES = ["Apparel", "Gadgets", "Gifts", "Others"]
ESSENTIALS_SUBCATEGORIES = ["Household", "Groceries", "Utilities", "Others"]



# Create an instance of the bot
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)



# Define the view with buttons for categories
class CategoryView(discord.ui.View):
    def __init__(self, transaction):
        super().__init__()
        self.transaction = transaction

    @discord.ui.button(label="Transport", style=discord.ButtonStyle.secondary)
    async def transport_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await self.show_subcategories(interaction, "Transport", TRANSPORT_SUBCATEGORIES)

    @discord.ui.button(label="Food", style=discord.ButtonStyle.primary)
    async def food_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await self.show_subcategories(interaction, "Food", FOOD_SUBCATEGORIES)

    @discord.ui.button(label="Essentials", style=discord.ButtonStyle.primary)
    async def essentials_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await self.show_subcategories(interaction, "Essentials", ESSENTIALS_SUBCATEGORIES)

    @discord.ui.button(label="Shopping", style=discord.ButtonStyle.success)
    async def shopping_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await self.show_subcategories(interaction, "Shopping", SHOPPING_SUBCATEGORIES)

    async def show_subcategories(
        self, interaction: discord.Interaction, category: str, subcategories: list
    ):
        for child in self.children:
            child.disabled = True
        await interaction.message.edit(
            view=self
        )  

        subcategory_view = SubcategoryView(self.transaction, category, subcategories)

        await interaction.response.send_message(
            content=f"Please sub-categorize this transaction as {category}-:",
            view=subcategory_view,
            
        )
    

class SubcategoryView(discord.ui.View):
    def __init__(self, transaction, category, subcategories):
        super().__init__()
        self.transaction = transaction
        self.category = category
        self.subcategories = subcategories

        # Create buttons for subcategories
        for subcategory in subcategories:
            self.add_item(
                discord.ui.Button(
                    label=subcategory,
                    style=discord.ButtonStyle.primary,
                    custom_id=subcategory,
                )
            )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        # Handle interaction for subcategory buttons
        for subcategory in self.subcategories:
            if interaction.data["custom_id"] == subcategory:
                await self.ask_for_remark(interaction, subcategory)

                for child in self.children:
                    child.disabled = True
                await interaction.message.edit(view=self)

                return False  # Stop processing after the category is set
        return True


    async def ask_for_remark(self, interaction: discord.Interaction, subcategory: str):
        # Ask user if they want to add a remark
        remark_view = RemarkOptionView(self.transaction, self.category, subcategory)
        await interaction.response.send_message(
            content="Would you like to add remarks?", view=remark_view,
        )
    
    async def save_category(self, interaction: discord.Interaction, subcategory: str, remarks=None):
        # Save the transaction with the category and subcategory
        transaction = self.transaction
        transaction["category"] = self.category
        transaction["subcategory"] = subcategory
        if remarks:
            transaction["remarks"] = remarks

        # Send the transaction to n8n
        send_transaction_to_n8n(transaction)
        remove_transaction_from_transaction_list(transaction)

        await interaction.response.send_message(
            content=f"Transaction saved with category: {self.category} and subcategory: {subcategory}"
        )


class RemarkOptionView(discord.ui.View):
    def __init__(self, transaction, category, subcategory):
        super().__init__()
        self.transaction = transaction
        self.category = category
        self.subcategory = subcategory

    @discord.ui.button(label="Yes", style=discord.ButtonStyle.primary)
    async def yes_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.disbale_buttons(interaction)
        await interaction.response.send_modal(RemarkModal(self.transaction, self.category, self.subcategory))

    @discord.ui.button(label="No", style=discord.ButtonStyle.secondary)
    async def no_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.disbale_buttons(interaction)
        await SubcategoryView(self.transaction, self.category, []).save_category(interaction, self.subcategory)

    async def disbale_buttons(self, interaction: discord.Interaction):
        for child in self.children:
            child.disabled = True
        await interaction.message.edit(view=self)

        
class RemarkModal(discord.ui.Modal):
    def __init__(self, transaction, category, subcategory):
        super().__init__(title="Enter your remarks")
        self.transaction = transaction
        self.category = category
        self.subcategory = subcategory

        self.remark_input = discord.ui.TextInput(
            label="Remarks", 
            placeholder="Enter your remarks here"
        )
        self.add_item(self.remark_input)

    async def on_submit(self, interaction: discord.Interaction):
        remark = self.remark_input.value
        await SubcategoryView(self.transaction, self.category, []).save_category(interaction, self.subcategory, remark)


def get_transactions():
    headers = {
        "Authorization": f"Bearer {AUTH_TOKEN}",
        "Content-Type": "application/json",
    }

    response = requests.get(EDGE_CACHE_URL, headers=headers).json()

    transactions = response["value"]

    return transactions


async def send_transaction_message_to_discord(channel, transaction):
    reference = transaction["reference"]
    message = (
        f"Transaction ID: {reference}\n"
        f"Date-Time: {transaction['date']}-{transaction['time']}\n"
        f"Amount: {transaction['amount']}\n"
        f"Recipient: {transaction['recipient']}\n\n"
        f"Please categorize this transaction:"
    )

    view = CategoryView(transaction)
    await channel.send(content=message, view=view)


async def process_transactions(transactions_list):
    for transaction in transactions_list:
        await send_transaction_message_to_discord(bot.get_channel(DISCORD_CHANNEL_ID), transaction)


def send_transaction_to_n8n(transaction):
    webhook_url = ADD_TRANSACTION_WEBHOOK_URL

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {AUTH_TOKEN}",
    }
    response = requests.post(webhook_url, headers=headers, json=transaction)

    response.raise_for_status()


def update_transaction_cache(transactions):
    url = "https://edge.adhirajpandey.me/cache"
    headers = {
        "Authorization" : f"Bearer {AUTH_TOKEN}",
        "Content-Type": "application/json"
    }
    data = {
        "key": "unsaved-transactions",
        "value": transactions
    }
    response = requests.post(url, headers=headers, json=data)
    response.raise_for_status()

def remove_transaction_from_transaction_list(transaction):
    global transactions_list
    new_transaction_list = [t for t in transactions_list if t["uuid"] != transaction["uuid"]]
            
    update_transaction_cache(new_transaction_list)


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    while True:
        global transactions_list
        transactions_list = get_transactions()
        print(f"Total transactions received from edge cache = {len(transactions_list)}")
        await process_transactions(transactions_list)
        await asyncio.sleep(SLEEP_TIME_IN_MINUTES*60) 

if __name__ == "__main__":
    transactions_list = []
    bot.run(DISCORD_BOT_TOKEN)
