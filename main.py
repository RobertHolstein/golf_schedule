import os
from dotenv import load_dotenv, find_dotenv
import discord
from discord.ext import commands, tasks
import requests_async as requests
import urllib.parse
from tabulate import tabulate
import asyncio
from datetime import datetime
import pandas as pd
import math


load_dotenv()
bot_token = os.getenv('BOT_TOKEN')
channel_id = os.getenv('CHANNEL_ID')
courses = os.getenv('COURSES').split(",")

intents = discord.Intents.all()
bot = commands.Bot(command_prefix='!', intents=intents)

@bot.command()
async def teetimestable(ctx, number_of_players: str, date_min: str, date_max: str, time_min: str, time_max: str):
    tee_times = await get_all_tee_times_date_time(courses, number_of_players, date_min, date_max, time_min, time_max)
    if tee_times:
        tee_times = remove_link_from_tee_times(tee_times)
        number_of_rows_to_send = 10
        rows_by = math.ceil(len(tee_times)/number_of_rows_to_send)
        for i in range(rows_by):
            row_start = i * number_of_rows_to_send
            row_end = row_start + number_of_rows_to_send
            if (row_end > len(tee_times)):
                row_end = len(tee_times) - 1
            print(tabulate_tee_times(tee_times[row_start:row_end], True))
            table = tabulate_tee_times(tee_times[row_start:row_end], True)
            await ctx.send(f"```{table}```")
    else:
        await ctx.send(f"No tee times available from date {date_min} to {date_max} and between times {time_min} to {time_max}.")

@bot.command()
async def teetimesembed(ctx, number_of_players: str, date_min: str, date_max: str, time_min: str, time_max: str):
    tee_times = await get_all_tee_times_date_time(courses, number_of_players, date_min, date_max, time_min, time_max)
    if tee_times:
        for tee_time in tee_times:
            embed = discord.Embed(title="Tee Time Available!", url=tee_time[6], color=0x00ff00)
            embed.add_field(name="Course", value=tee_time[0], inline=False)
            embed.add_field(name="Date", value=tee_time[1], inline=False)
            embed.add_field(name="Time", value=tee_time[2], inline=False)
            format_string = f"Course: {tee_time[0]}\rDate: {tee_time[1]}\rTime: {tee_time[2]}"           
            message = await ctx.send(embed=embed)
        check_tee_times.stop()
    else:
        await ctx.send(f"No tee times available from date {date_min} to {date_max} and between times {time_min} to {time_max}.")

@bot.command()
async def teetimes(ctx, number_of_players: str, date_min: str, date_max: str, time_min: str, time_max: str):
    tee_times = await get_all_tee_times_date_time(courses, number_of_players, date_min, date_max, time_min, time_max)
    channel = await bot.fetch_channel(channel_id)
    if tee_times:
        message = await ctx.send(f":golf::man_golfing:")
        thread = await message.create_thread(name="Tee Time")
        for tee_time in tee_times:
            await thread.send(f"----------------------------------------")
            await thread.send(tee_time[6])
            del tee_time[6]
            table = tabulate_tee_times([tee_time], True)
            format_string = f"Course: {tee_time[0]}\rDate: {tee_time[1]}\rTime: {tee_time[2]}"
            await thread.send(f"```{format_string}```")
            await thread.send(f"----------------------------------------")
        check_tee_times.stop()
    else:
        await channel.send(f"No tee times available from date {date_min} to {date_max} and between times {time_min} to {time_max}.")

@bot.command()
async def teetimerequest(ctx, number_of_players: str, date_min: str, date_max: str, time_min: str, time_max: str):
    check_tee_times.stop()
    check_tee_times.start(number_of_players, date_min, date_max, time_min, time_max)
    await ctx.send(f"Will check for open spots at that date and time.")


@tasks.loop(minutes=30)
async def check_tee_times(number_of_players: str, date_min: str, date_max: str, time_min: str, time_max: str):
    tee_times = await get_all_tee_times_date_time(courses, number_of_players, date_min, date_max, time_min, time_max)
    channel = await bot.fetch_channel(channel_id)
    if tee_times:
        message = await channel.send(f"@here :golf::man_golfing:")
        thread = await message.create_thread(name="Tee Time")
        for tee_time in tee_times:
            await thread.send(f"----------------------------------------")
            await thread.send(tee_time[6])
            del tee_time[6]
            table = tabulate_tee_times([tee_time], True)
            format_string = f"Course: {tee_time[0]}\rDate: {tee_time[1]}\rTime: {tee_time[2]}"
            await thread.send(f"```{format_string}```")
            await thread.send(f"----------------------------------------")
        check_tee_times.stop()
    else:
        await channel.send(f"No tee times available from date {date_min} to {date_max} and between times {time_min} to {time_max} will check again in 30 minutes.")


@bot.listen()
async def on_ready():
    print("Bot ready!")

async def get_teetimes_for_course(courseName: str, date: str, number_of_players: str):
    # Replace dashes with spaces and encode string
    courseName = urllib.parse.quote_plus(courseName)
    date = urllib.parse.quote_plus(date)

    url = f"https://sg-membership20-portalapi-production.azurewebsites.net/api/courses/reservations_group?allCartSelected=true&allRatesSelected=true&date={date}&max_hour=21&max_price=500&min_hour=5&min_price=0&slug={courseName}&programId=57&qty={number_of_players}"
    response = await requests.get(url)
    data = response.json()

    # Extract the relevant data from the response
    if data['tee_time_groups']:
        tee_time_groups = []
        for tee_time in data['tee_time_groups']:
            course = courseName.replace("-", " ").rsplit(" ", 1)[0]
            date = f"{tee_time['tee_off_at_local'].split('T')[0]}"
            time = f"{tee_time['tee_off_at_local'].split('T')[1]}"
            starting_rate = f"{tee_time['symbol']}{tee_time['starting_rate']:.2f}"
            max_regular_rate = f"{tee_time['symbol']}{tee_time['max_regular_rate']:.2f}"
            players = ', '.join(map(str, tee_time['players']))

            time_obj = datetime.strptime(tee_time['tee_off_at_local'], "%Y-%m-%dT%H:%M:%S.%fZ")
            link = tee_time_rates_link_generator(courseName, course, tee_time['players'], time_obj)
            
            tee_time_groups.append([course,
                                          date,
                                          time,
                                          starting_rate,
                                          max_regular_rate,
                                          players,
                                          link
                                        ])
        return tee_time_groups


async def get_all_tee_times_date_time(courses: list, number_of_players: str, date_min: str, date_max: str, time_min: str, time_max: str):
    start = datetime.strptime(date_min, "%Y-%m-%d")
    end = datetime.strptime(date_max, "%Y-%m-%d")
    dates = pd.date_range(start,end).to_pydatetime().tolist()

    all_tee_times = []
    for course in courses:
        for date in dates:
            tee_time_for_course = await get_teetimes_for_course(course, date.strftime("%Y-%m-%d"), number_of_players)
            if tee_time_for_course:
                all_tee_times.extend(tee_time_for_course)

    tee_times_between_times = []
    for tee_time in all_tee_times:
        if datetime.strptime(time_min, '%H:%M') <= datetime.strptime(tee_time[2], '%H:%M:%S.%fZ') <= datetime.strptime(time_max, '%H:%M'):
            tee_times_between_times.append(tee_time)

    return tee_times_between_times

def tabulate_tee_times(tee_times: list, print_header = True):
    if print_header:
        return tabulate(tee_times, headers=['course',
                                        'date',
                                        'time',
                                        'starting_rate',
                                        'max_regular_rate',
                                        'players',
                                        ])
    return tabulate(tee_times)

def tee_time_rates_link_generator(full_course_name: str, course_name: str, players: list, date_time: datetime):
        date_slot = date_time.strftime("%Y-%m-%d")
        time_slot = date_time.strftime("%I:%M:%S %p")
        if len(players) == 1:
            players_string = "1"
        else:
            players_string = f"{min(players)} - {max(players)}"
        body = f"allCartSelected=true&allRatesSelected=true&courseName={course_name}&date={date_slot}&holesGroupText=18&max_hour=21&max_price=500&min_hour=5&min_price=0&playersGroupText={players_string}&time_slot={time_slot}&transportText=Cart Available"
        body_encoded = urllib.parse.quote_plus(body, safe='=&')
        return f"https://letsgo.golf/recreation-park-golf-course-18/teeTimeRates/at/{full_course_name}?{body_encoded}"

def remove_link_from_tee_times(tee_times: list):
    new_tee_times = []
    for tee_time in tee_times:
        del tee_time[6]
        new_tee_times.append(tee_time)
    return new_tee_times

if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.create_task(bot.start(bot_token))
    loop.run_forever()