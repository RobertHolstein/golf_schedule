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
import pytz

load_dotenv()
BOT_TOKEN = os.getenv('BOT_TOKEN')
CHANNEL_ID = os.getenv('CHANNEL_ID')
COURSES = os.getenv('COURSES').split(",")
PROGRAM_ID = os.getenv('PROGRAM_ID')
USER = os.getenv('USER')
PASSWORD = os.getenv('PASSWORD')
TOKEN = ""
INTERVAL_MINUTES = int(os.getenv('INTERVAL_MINUTES'))
LAST_FOUR = os.getenv('LAST_FOUR')
ALLOWED_USERS = set(map(int, os.getenv('ALLOWED_USERS').split(',')))

intents = discord.Intents.all()
bot = commands.Bot(command_prefix='!', intents=intents)

def is_allowed_user():
    async def predicate(ctx):
        if ctx.author.id in ALLOWED_USERS:
            return True
        else:
            await ctx.send(f"{ctx.author.mention} you are not allowed to use this command.")
            return False
    return commands.check(predicate)

@bot.command()
async def courses(ctx):
    # Create a message string that lists the courses with their index number
    courses_list = "\n".join([f"{index}: {course}" for index, course in enumerate(COURSES)])
    
    # Send the courses list to the user
    await ctx.send(f"List of available courses:\n```{courses_list}```")

@bot.command()
async def teetimestable(ctx, number_of_players: str, date_min: str, date_max: str, time_min: str, time_max: str):
    tee_times = await get_all_tee_times_date_time(COURSES, number_of_players, date_min, date_max, time_min, time_max)
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
    tee_times = await get_all_tee_times_date_time(COURSES, number_of_players, date_min, date_max, time_min, time_max)
    if tee_times:
        for tee_time in tee_times:
            embed = discord.Embed(title="Tee Time Available!", url=tee_time[6], color=0x00ff00)
            embed.add_field(name="Course", value=tee_time[0], inline=False)
            embed.add_field(name="Date", value=tee_time[1], inline=False)
            embed.add_field(name="Time", value=tee_time[2], inline=False)
            format_string = f"Course: {tee_time[0]}\rDate: {tee_time[1]}\rTime: {tee_time[2]}"           
            message = await ctx.send(embed=embed)
        search_tee_times_loop.stop()
    else:
        await ctx.send(f"No tee times available from date {date_min} to {date_max} and between times {time_min} to {time_max}.")

@bot.command()
async def teetimes(ctx, number_of_players: str, date_min: str, date_max: str, time_min: str, time_max: str):
    tee_times = await get_all_tee_times_date_time(COURSES, number_of_players, date_min, date_max, time_min, time_max)
    channel = await bot.fetch_channel(CHANNEL_ID)
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
        search_tee_times_loop.stop()
    else:
        await channel.send(f"No tee times available from date {date_min} to {date_max} and between times {time_min} to {time_max}.")

@bot.command()
async def requestinterval(ctx, interval_minutes: int):
    search_tee_times_loop.change_interval(minutes=interval_minutes)
    channel = await bot.fetch_channel(CHANNEL_ID)
    await channel.send(f":golf::man_golfing: The tee time request interval has been changed to {interval_minutes}. If you had a tee time request going, it will continue with the new interval.")

@bot.command()
@is_allowed_user()
async def search(ctx, course_ids_string: str, number_of_players: str, date_min: str, date_max: str, time_min: str, time_max: str):
    if search_tee_times_loop.is_running():
        stop_search_tee_times_loop()
    should_book = False
    search_tee_times_loop.start(course_ids_string, number_of_players, date_min, date_max, time_min, time_max, should_book)
    await ctx.send(f":golf::man_golfing: Checking for open spots at that date and time.")

@bot.command()
@is_allowed_user()
async def searchandbook(ctx, course_ids_string: str, number_of_players: str, date_min: str, date_max: str, time_min: str, time_max: str):
    if search_tee_times_loop.is_running():
        stop_search_tee_times_loop()
    should_book = True
    search_tee_times_loop.start(course_ids_string, number_of_players, date_min, date_max, time_min, time_max, should_book)
    await ctx.send(f":golf::man_golfing: Checking for open spots at that date and time. If a tee time is found it will be booked")

@bot.command()
@is_allowed_user()
async def cancel(ctx, booking_id):
    await cancel_booking(booking_id)

@tasks.loop(minutes=INTERVAL_MINUTES)
async def search_tee_times_loop(course_ids_string: str, number_of_players: str, date_min: str, date_max: str, time_min: str, time_max: str, should_book: bool):
    try:
        if search_tee_times_loop.current_loop == 0:
            search_tee_times_loop.loop_params = {
                'course_ids_string': course_ids_string,
                'number_of_players': number_of_players,
                'date_min': date_min,
                'date_max': date_max,
                'time_min': time_min,
                'time_max': time_max,
                'should_book': should_book,
                'start_time': datetime.now()
            }

        courses = select_courses(course_ids_string.split(','), COURSES)
        tee_times = await get_all_tee_times_date_time(courses, number_of_players, date_min, date_max, time_min, time_max)
        if tee_times:
            channel = await bot.fetch_channel(CHANNEL_ID)
            if should_book:
                earliest_tee_time = min(tee_times, key=lambda x: x['date_time'])
                rates = await get_teetime_rates(earliest_tee_time['full_course_name'], earliest_tee_time['course'], number_of_players, earliest_tee_time['date_time'])
                regular_rate = next(rate for rate in rates if rate['type'] == 'is_regular_rate')
                
                tee_time = await get_tee_times(
                                regular_rate['num_holes'],
                                regular_rate['cart_type'],
                                regular_rate['major_rate_type'],
                                regular_rate['minor_rate_type'],
                                earliest_tee_time['date_time'],
                                number_of_players,
                                earliest_tee_time['full_course_name'])
                
                the_tee_time = tee_time['tee_times'][0]

                reservation = await prepare_reservation(number_of_players, True, the_tee_time['uuid'], the_tee_time['tee_off_at_local'], the_tee_time['id'])
                user_info =  await get_user_info()
                credit_cards = await get_credit_cards()
                selected_credit_card = next((card for card in credit_cards if card['last_four'] == LAST_FOUR), None)
                booking = await book_tee_time(reservation['token'], selected_credit_card['id'], user_info['firstName'], user_info['lastName'], user_info['email'])
                message = (
                    f"@here\n"
                    f":golf: **TEE TIME BOOKED** :man_golfing:\n"
                    f"```"
                    f"Course           : {booking['offer']['course_name']}\n"
                    f"Tee Off Time     : {booking['offer']['tee_time']['tee_off_at_local']}\n"
                    f"Number of Players: {booking['offer']['qty']}\n"
                    f"Rate             : {booking['offer']['rate']['symbol']}{booking['offer']['rate']['amount']} {booking['offer']['rate']['currency']}\n"
                    f"Total Due        : {booking['offer']['total_due']['symbol']}{booking['offer']['total_due']['amount']} {booking['offer']['total_due']['currency']}\n"
                    f"Cancel prompt    : !cancel {booking['reservation_id']}\n"
                    f"```"
                )
                message = await channel.send(message)
            else:
                message = await channel.send(f"@here :golf: **TEE TIME(S) FOUND** :man_golfing:")
                thread = await message.create_thread(name="Tee Time")
                for tee_time in tee_times:
                    await thread.send(f"----------------------------------------")
                    await thread.send(f"{tee_time['link']}")
                    await thread.send(f"```Course: {tee_time['course']}\rDate and Time: {tee_time['date_time']}```")
                    await thread.send(f"----------------------------------------")
            # else:
            #     await channel.send(f"No tee times available from date {date_min} to {date_max} and between times {time_min} to {time_max} will check again in 30 minutes.")
            stop_search_tee_times_loop()
    except asyncio.CancelledError:
        search_tee_times_loop.loop_params = None
    except Exception as e:
        # Log or handle the exception as needed.
        print(f"An error occurred: {e}")
        search_tee_times_loop.loop_params = None

@bot.command()
async def stop(ctx):
    if search_tee_times_loop.is_running():
        stop_search_tee_times_loop()
        await ctx.send("The tee time search loop has been stopped.")

@bot.command()
async def status(ctx):
    status_message = check_status()
    await ctx.send(status_message)

def check_status():
    if search_tee_times_loop.is_running():
        params = search_tee_times_loop.loop_params
        utc = pytz.UTC
        start_time = params['start_time'].astimezone(utc).strftime("%Y-%m-%d %H:%M:%S")
        next_run = search_tee_times_loop.next_iteration.astimezone(utc).strftime("%Y-%m-%d %H:%M:%S")
        status_message = (
            "The tee time search loop is currently running with the following parameters:\n"
            f"```"
            f"Start Time:        {start_time} UTC\n"
            f"Next Run Time:     {next_run} UTC\n"
            f"Sleep Minutes:     {INTERVAL_MINUTES}\n"
            f"Current Loop:      {search_tee_times_loop.current_loop + 1}\n"
            f"Course IDs:        {params['course_ids_string']}\n"
            f"Number of players: {params['number_of_players']}\n"
            f"Date range:        {params['date_min']} - {params['date_max']}\n"
            f"Time range:        {params['time_min']} - {params['time_max']}\n"
            f"Should book:       {'Yes' if params['should_book'] else 'No'}"
            f"```"
        )
    else:
        status_message = "The tee time search loop is not running."
    return status_message

def stop_search_tee_times_loop():
    search_tee_times_loop.cancel()
    search_tee_times_loop.loop_params = None

@bot.listen()
async def on_ready():
    global TOKEN
    TOKEN = await get_login_token(PROGRAM_ID, USER, PASSWORD)   
    print("Bot ready!")


async def get_login_token(program_id, username, password):
    url = f"https://sg-membership20-portalapi-production.azurewebsites.net/api/authentication/signin?programId={program_id}"
    headers = {
        "Content-Type": "application/json"
    }
    payload = {
        "programId": program_id,
        "username": username,
        "password": password
    }
    response = await requests.post(url, headers=headers, json=payload)
    response_json = response.json()
    return response_json['token']

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
            full_course_name = courseName
            course = courseName.replace("-", " ").rsplit(" ", 1)[0]
            date_format = "%Y-%m-%dT%H:%M:%S.%fZ"
            date_time = datetime.strptime(tee_time['tee_off_at_local'], date_format)
            date = f"{tee_time['tee_off_at_local'].split('T')[0]}"
            time = f"{tee_time['tee_off_at_local'].split('T')[1]}"
            starting_rate = f"{tee_time['symbol']}{tee_time['starting_rate']:.2f}"
            max_regular_rate = f"{tee_time['symbol']}{tee_time['max_regular_rate']:.2f}"
            players = ', '.join(map(str, tee_time['players']))

            time_obj = datetime.strptime(tee_time['tee_off_at_local'], "%Y-%m-%dT%H:%M:%S.%fZ")
            link = tee_time_rates_link_generator(courseName, course, tee_time['players'], time_obj)
            
            tee_time_group = {
                "full_course_name": full_course_name,
                "course": course,
                "date_time": date_time,
                "starting_rate": starting_rate,
                "max_regular_rate": max_regular_rate,
                "players": players,
                "link": link
            }
            tee_time_groups.append(tee_time_group)
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
    time_min_dt = datetime.strptime(time_min, '%H:%M').time()
    time_max_dt = datetime.strptime(time_max, '%H:%M').time()
    for tee_time in all_tee_times:
        if time_min_dt <= tee_time['date_time'].time() <= time_max_dt:
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

async def get_user_info():
    url = f"https://sg-membership20-portalapi-production.azurewebsites.net/api/userProfile?programId={PROGRAM_ID}"
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json;charset=UTF-8",
        "x-api-user-token": TOKEN
    }
    response = await requests.get(url, headers=headers)
    data = response.json()
    return data

async def get_credit_cards():
    url = f"https://sg-membership20-portalapi-production.azurewebsites.net/api/payment/creditcards?programId={PROGRAM_ID}"
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json;charset=UTF-8",
        "x-api-user-token": TOKEN
    }
    response = await requests.get(url, headers=headers)
    data = response.json()
    return data

async def book_tee_time(reservation_id, credit_card_id, first_name, last_name, email):
    url = f"https://sg-membership20-portalapi-production.azurewebsites.net/api/reservation/{reservation_id}?&programId={PROGRAM_ID}"
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json;charset=UTF-8",
        "x-api-user-token": TOKEN
    }
    payload = {
        "credit_card_id": credit_card_id,
        "userReservationsDetails": {
            "FirstName": first_name,
            "LastName": last_name,
            "Email": email
        }
    }
    response = await requests.post(url, headers=headers, json=payload)
    data = response.json()
    return data['receipt']

async def cancel_booking(booking_id):
    url = f"https://sg-membership20-portalapi-production.azurewebsites.net/api/reservation/cancel/{booking_id}?programId={PROGRAM_ID}"
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json;charset=UTF-8",
        "x-api-user-token": TOKEN
    }
    response = await requests.post(url, headers=headers)
    data = response.json()
    return data['reservation']

async def prepare_reservation(qty, with_default_credit_card, uuid, tee_time_date, tee_time_id):
    url = f"https://sg-membership20-portalapi-production.azurewebsites.net/api/courses/tee_times/{tee_time_id}/reservations/prepare?programId={PROGRAM_ID}"
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json;charset=UTF-8",
        "x-api-user-token": TOKEN
    }
    payload = {
        "qty": qty,
        "with_default_credit_card": with_default_credit_card,
        "uuid": uuid,
        "teeTimeDate": tee_time_date
    }
    response = await requests.post(url, headers=headers, json=payload)
    data = response.json()
    return data['prepared_tee_time']

async def get_teetime_rates(full_course_name: str, course_name: str, players: list, date_time: datetime):
    date_slot = date_time.strftime("%Y-%m-%d")
    time_slot = date_time.strftime("%I:%M:%S %p")
    params = {
        "courseName": course_name,
        "date": date_slot,
        "is_riding": None,
        "max_price": "500",
        "min_price": "0",
        "slug": full_course_name,
        "time_slot": time_slot,
        "programId": PROGRAM_ID
    }
    url = "https://sg-membership20-portalapi-production.azurewebsites.net/api/courses/tee_time_groups_rate_types"
    headers = {
        "Accept": "application/json, text/plain, */*",
        "x-api-user-token": TOKEN
    }
    response = await requests.get(url, params=params, headers=headers)
    data = response.json()
    return data['rates']

async def get_tee_times(num_holes, cart_type, major_rate_type, minor_rate_type, date_time, qty, full_course_name):
    date_slot = date_time.strftime("%Y-%m-%d")
    time_slot = date_time.strftime("%I:%M:%S %p")
    is_riding = True if cart_type == 'is_riding' else False
    
    params = {
        "date": date_slot,
        "is_riding": is_riding,
        "major_rate_type": major_rate_type,
        "minor_rate_type": minor_rate_type,
        "num_holes": num_holes,
        "qty": qty,
        "slug": full_course_name,
        "time_slot": time_slot,
        "programId": PROGRAM_ID
    }
    url = "https://sg-membership20-portalapi-production.azurewebsites.net/api/courses/tee_time_at"
    headers = {
        "Accept": "application/json, text/plain, */*",
        "x-api-user-token": TOKEN
    }
    response = await requests.get(url, params=params, headers=headers)
    data = response.json()
    return data

def select_courses(index_strings, all_courses):
    indices = [int(index_str) for index_str in index_strings]
    selected_courses = [all_courses[index] for index in indices]
    return selected_courses

def remove_link_from_tee_times(tee_times: list):
    new_tee_times = []
    for tee_time in tee_times:
        del tee_time[6]
        new_tee_times.append(tee_time)
    return new_tee_times

if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.create_task(bot.start(BOT_TOKEN))
    loop.run_forever()