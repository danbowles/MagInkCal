#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
This script essentially generates a HTML file of the calendar I wish to display. It then fires up a headless Chrome
instance, sized to the resolution of the eInk display and takes a screenshot. This screenshot will then be processed
to extract the grayscale and red portions, which are then sent to the eInk display for updating.

This might sound like a convoluted way to generate the calendar, but I'm doing so mainly because (i) it's easier to
format the calendar exactly the way I want it using HTML/CSS, and (ii) I can better delink the generation of the
calendar and refreshing of the eInk display. In the future, I might choose to generate the calendar on a separate
RPi device, while using a ESP32 or PiZero purely to just retrieve the image from a file host and update the screen.
"""

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
import shutil
from time import sleep
from datetime import timedelta
import pathlib
from PIL import Image
import logging
from calendar import monthrange


class RenderHelper:

    def __init__(self, width, height, angle):
        self.logger = logging.getLogger("maginkcal")
        self.currPath = str(pathlib.Path(__file__).parent.absolute())
        self.htmlFile = "file://" + self.currPath + "/calendar.html"
        self.imageWidth = width
        self.imageHeight = height
        self.rotateAngle = angle

    def set_viewport_size(self, driver):

        # Extract the current window size from the driver
        current_window_size = driver.get_window_size()

        # Extract the client window size from the html tag
        html = driver.find_element(By.TAG_NAME, "html")
        inner_width = int(html.get_attribute("clientWidth"))
        inner_height = int(html.get_attribute("clientHeight"))

        # "Internal width you want to set+Set "outer frame width" to window size
        target_width = self.imageWidth + (current_window_size["width"] - inner_width)
        target_height = self.imageHeight + (
            current_window_size["height"] - inner_height
        )

        driver.set_window_rect(width=target_width, height=target_height)

    def get_screenshot(self):
        from selenium.webdriver.chrome.service import Service

        chrome_path = shutil.which("chromium-browser")
        driver_path = shutil.which("chromedriver")

        if not chrome_path:
            raise FileNotFoundError("Could not find chromium-browser in PATH")
        if not driver_path:
            raise FileNotFoundError("Could not find chromedriver in PATH")

        opts = Options()
        opts.binary_location = chrome_path
        opts.add_argument("--headless")
        opts.add_argument("--hide-scrollbars")
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")
        opts.add_argument("--force-device-scale-factor=1")

        service = Service(executable_path=driver_path)
        driver = webdriver.Chrome(service=service, options=opts)

        try:
            self.set_viewport_size(driver)
            driver.get(self.htmlFile)
            sleep(1)
            driver.get_screenshot_as_file(self.currPath + "/calendar.png")
        finally:
            driver.quit()

        self.logger.info("Screenshot captured and saved to file.")

        redimg = Image.open(self.currPath + "/calendar.png")  # get image)
        rpixels = redimg.load()  # create the pixel map
        blackimg = Image.open(self.currPath + "/calendar.png")  # get image)
        bpixels = blackimg.load()  # create the pixel map

        for i in range(redimg.size[0]):  # loop through every pixel in the image
            for j in range(
                redimg.size[1]
            ):  # since both bitmaps are identical, cycle only once and not both bitmaps
                if (
                    rpixels[i, j][0] <= rpixels[i, j][1]
                    and rpixels[i, j][0] <= rpixels[i, j][2]
                ):  # if is not red
                    rpixels[i, j] = (
                        255,
                        255,
                        255,
                    )  # change it to white in the red image bitmap

                elif (
                    bpixels[i, j][0] > bpixels[i, j][1]
                    and bpixels[i, j][0] > bpixels[i, j][2]
                ):  # if is red
                    bpixels[i, j] = (
                        255,
                        255,
                        255,
                    )  # change to white in the black image bitmap

        redimg = redimg.rotate(self.rotateAngle, expand=True)
        blackimg = blackimg.rotate(self.rotateAngle, expand=True)

        self.logger.info("Image colours processed. Extracted grayscale and red images.")
        return blackimg, redimg

    def get_day_in_cal(self, startDate, eventDate):
        delta = eventDate - startDate
        return delta.days

    def get_short_time(self, datetimeObj, is24hour=False):
        datetime_str = ""
        if is24hour:
            datetime_str = "{}:{:02d}".format(datetimeObj.hour, datetimeObj.minute)
        else:
            if datetimeObj.minute > 0:
                datetime_str = ".{:02d}".format(datetimeObj.minute)

            if datetimeObj.hour == 0:
                datetime_str = "12{}am".format(datetime_str)
            elif datetimeObj.hour == 12:
                datetime_str = "12{}pm".format(datetime_str)
            elif datetimeObj.hour > 12:
                datetime_str = "{}{}pm".format(str(datetimeObj.hour % 12), datetime_str)
            else:
                datetime_str = "{}{}am".format(str(datetimeObj.hour), datetime_str)
        return datetime_str

    def ordinal_suffix(n):
        if 11 <= n % 100 <= 13:
            return "th"
        return {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")

    def process_inputs(self, calDict):
        def ordinal_suffix(n):
            if 11 <= n % 100 <= 13:
                return "th"
            return {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")

        """
        calDict = {
            'calStartDate': calStartDate,
            'today': currDate,
            'lastRefresh': currDatetime,
            'batteryLevel': batteryLevel,
            'maxEventsPerDay': int,
            'dayOfWeekText': list of str,
            'weekStartDay': int,
            'is24hour': bool,
            'calendarMap': {
                'id_1': {'name': 'Ellie', 'icon': '♣︎', 'events': [...]},
                ...
            },
        }
        """
        # Initialize 35-day calendar list
        calList = [[] for _ in range(35)]

        maxEventsPerDay = calDict["maxEventsPerDay"]
        calendarMap = calDict["calendarMap"]
        batteryDisplayMode = calDict["batteryDisplayMode"]
        dayOfWeekText = calDict["dayOfWeekText"]
        weekStartDay = calDict["weekStartDay"]
        is24hour = calDict["is24hour"]
        calStartDate = calDict["calStartDate"]
        today = calDict["today"]

        legendHtml = ""
        for cal_id, info in calendarMap.items():
            legendHtml += f'<div class="flex items-center"><span class="mr-1">{info["icon"]}</span>{info["name"]}</div>\n'

        # Merge and assign events to days
        for cal_id, cal_data in calendarMap.items():
            for event in cal_data["events"]:
                event["icon"] = cal_data["icon"]
                event["ownerName"] = cal_data["name"]
                idx = self.get_day_in_cal(calStartDate, event["startDatetime"].date())
                if 0 <= idx < len(calList):
                    calList[idx].append(event)
                if event["isMultiday"]:
                    end_idx = self.get_day_in_cal(
                        calStartDate, event["endDatetime"].date()
                    )
                    if 0 <= end_idx < len(calList):
                        calList[end_idx].append(event)

        # Read the template
        with open(self.currPath + "/calendar_template.html", "r") as file:
            calendar_template = file.read()

        # Format header
        month_year = today.strftime("%B %Y")
        weekday = today.strftime("%A")
        day = today.day
        weekday_day = f"{weekday}, {day}{ordinal_suffix(day)}"

        # batteryDisplayMode - 0: do not show / 1: always show / 2: show when battery is low
        battLevel = calDict["batteryLevel"]

        week_day_headers = "".join(
            f"<div>{dayOfWeekText[(i + weekStartDay) % 7]}</div>\n" for i in range(7)
        )
        
        # Calculate proper start and grid size
        month_start = today.replace(day=1)
        sunday_offset = (month_start.weekday() + 1) % 7
        calStartDate = month_start - timedelta(days=sunday_offset)

        end_of_month = today.replace(day=monthrange(today.year, today.month)[1])
        days_needed = (end_of_month - calStartDate).days + 1
        grid_size = 42 if days_needed > 35 else 35

        calendar_cells = []
        # Then:
        for i in range(grid_size):
            curr_date = calStartDate + timedelta(days=i)
            events = []

            for cal in calendarMap.values():
                for e in cal["events"]:
                    if e["startDatetime"].date() == curr_date:
                        events.append({**e, "icon": cal["icon"], "name": cal["name"]})

            events.sort(key=lambda e: e["startDatetime"])

            # Determine styling
            extra_classes = ' text-einkGray' if curr_date.month != today.month else ''
            day_cell = f'<div class="p-1 border border-gray-200{extra_classes}">'

            # Day number rendering
            if curr_date == today:
                day_cell += f'''
                <div class="flex justify-between items-center mb-1">
                <div class="w-6 h-6 text-center leading-6 rounded-full font-bold text-white bg-einkRed">{curr_date.day}</div>
                </div>
                '''
            else:
                day_cell += f'<div class="mb-1 font-bold">{curr_date.day}</div>\n'

            # Event rendering
            for e in events[:maxEventsPerDay]:
                if e['allday']:
                    label = f'{e["icon"]} {e["summary"]}'
                else:
                    t = e["startDatetime"]
                    time_str = f'{t.hour:02d}:{t.minute:02d}' if is24hour else f'{t.hour % 12 or 12}{"a" if t.hour < 12 else "p"}'
                    label = f'{e["icon"]} {time_str} {e["summary"]}'
                day_cell += f'<div class="whitespace-nowrap overflow-hidden text-ellipsis">{label}</div>\n'

            # Overflow indicator
            if len(events) > maxEventsPerDay:
                day_cell += f'<div class="text-einkGray text-xs">{len(events) - maxEventsPerDay} more</div>'

            day_cell += '</div>'
            calendar_cells.append(day_cell.strip())

            
        # Append the bottom and write the file
        htmlFile = open(self.currPath + "/calendar.html", "w")
        htmlFile.write(
            calendar_template.format(
                month_year=month_year,
                weekday_day=weekday_day,
                week_day_headers=week_day_headers,
                batt_level_percent=f"{battLevel}%",
                legendHtml=legendHtml,
                events='\n'.join(calendar_cells),
            )
        )
        htmlFile.close()

        calBlackImage, calRedImage = self.get_screenshot()

        return calBlackImage, calRedImage
