import os
from dotenv import load_dotenv, find_dotenv
import discord
from discord.ext import commands, tasks
import requests
import urllib.parse
from tabulate import tabulate
import asyncio

load_dotenv()
bot_token = os.getenv('BOT_TOKEN')
channel_id = os.getenv('CHANNEL_ID')

intents = discord.Intents.all()
bot = commands.Bot(command_prefix='!', intents=intents)

@bot.command()
async def teetimes(ctx, courseName: str, date: str, time_slot: str):
    # Replace dashes with spaces and encode string
    courseName = courseName.replace('-', ' ')
    # date = date.replace('-', ' ')
    time_slot = time_slot.replace('-', ' ')
    courseName = urllib.parse.quote_plus(courseName)
    date = urllib.parse.quote_plus(date)
    time_slot = urllib.parse.quote_plus(time_slot)

    url = f"https://sg-membership20-portalapi-production.azurewebsites.net/api/courses/tee_time_groups_rate_types?courseName={courseName}&date={date}&is_riding&max_price=500&min_price=0&num_holes=18&qty=4&slug=recreation-park-golf-course-18-california&time_slot={time_slot}&programId=57"
    response = requests.get(url)
    data = response.json()

    # Extract the relevant data from the response
    rates = []
    for rate in data['rates']:
        rate_type = rate['rate_type_label']
        rate_price = f"{rate['symbol']}{rate['rate']:.2f}"
        rate_players = ', '.join(map(str, rate['players']))
        rates.append([rate_type, rate_price, rate_players])

    # Format the data into a table
    table = tabulate(rates, headers=['Rate Type', 'Price', 'Players'])

    # Send the table in a Discord message
    await ctx.send(f"Here are the available tee times for {courseName} on {date} at {time_slot}:\n```{table}```")

@tasks.loop(seconds=10)
async def check_tee_times():
    courseName = 'recreation-park-golf-course-18-california'
    date = '2023-03-10'
    time_slot = '6:20:00-AM'
    courseName = courseName.replace('-', ' ')
    time_slot = time_slot.replace('-', ' ')
    courseName = urllib.parse.quote_plus(courseName)
    date = urllib.parse.quote_plus(date)
    time_slot = urllib.parse.quote_plus(time_slot)
    url = f"https://sg-membership20-portalapi-production.azurewebsites.net/api/courses/tee_time_groups_rate_types?courseName={courseName}&date={date}&is_riding&max_price=500&min_price=0&num_holes=18&qty=4&slug=recreation-park-golf-course-18-california&time_slot={time_slot}&programId=57"
    response = requests.get(url)
    data = response.json()
    if data['rates']:
        rates = []
        for rate in data['rates']:
            rate_type = rate['rate_type_label']
            rate_price = f"{rate['symbol']}{rate['rate']:.2f}"
            rate_players = ', '.join(map(str, rate['players']))
            rates.append([rate_type, rate_price, rate_players])
        
    # Format the data into a table
    table = tabulate(rates, headers=['Rate Type', 'Price', 'Players'])

    channel = await bot.fetch_channel(channel_id)
    # Send the table in a Discord message
    await channel.send(f"ATTENTION: There are available tee times for {courseName} on {date} at {time_slot}:\n```{table}```")

@bot.listen()
async def on_ready():
    check_tee_times.start()

if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.create_task(bot.start(bot_token))
    loop.run_forever()