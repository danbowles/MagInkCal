#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
This project is designed for the WaveShare 12.48" eInk display. Modifications will be needed for other displays,
especially the display drivers and how the image is being rendered on the display. Also, this is the first project that
I posted on GitHub so please go easy on me. There are still many parts of the code (especially with timezone
conversions) that are not tested comprehensively, since my calendar/events are largely based on the timezone I'm in.
There will also be work needed to adjust the calendar rendering for different screen sizes, such as modifying of the
CSS stylesheets in the "render" folder.
"""
import datetime as dt
import os
import sys

from pytz import timezone
from gcal.gcal import GcalHelper
from render.render import RenderHelper
from power.power import PowerHelper
import json
import logging


def setup_logger(display_tz):
    log_dir = os.environ.get("MAGINKCAL_LOG_DIR", "logs")
    os.makedirs(log_dir, exist_ok=True)

    run_started = dt.datetime.now(display_tz)
    timestamp = run_started.strftime("%Y%m%d-%H%M%S-%Z")
    log_file = os.path.join(log_dir, f"maginkcal-{timestamp}.log")

    logger = logging.getLogger("maginkcal")
    logger.handlers.clear()
    logger.propagate = False
    logger.setLevel(logging.INFO)

    formatter = logging.Formatter("%(asctime)s %(levelname)s - %(message)s")

    file_handler = logging.FileHandler(log_file, mode="a", encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    return logger, log_file


def main():
    # Basic configuration settings (user replaceable)
    configFile = open("config.json")
    config = json.load(configFile)

    displayTZ = timezone(
        config["displayTZ"]
    )  # list of timezones - print(pytz.all_timezones)
    thresholdHours = config[
        "thresholdHours"
    ]  # considers events updated within last 12 hours as recently updated
    maxEventsPerDay = config[
        "maxEventsPerDay"
    ]  # limits number of events to display (remainder displayed as '+X more')
    isDisplayToScreen = config[
        "isDisplayToScreen"
    ]  # set to true when debugging rendering without displaying to screen
    isShutdownOnComplete = config[
        "isShutdownOnComplete"
    ]  # set to true to conserve power, false if in debugging mode
    batteryDisplayMode = config[
        "batteryDisplayMode"
    ]  # 0: do not show / 1: always show / 2: show when battery is low
    weekStartDay = config["weekStartDay"]  # Monday = 0, Sunday = 6
    dayOfWeekText = config["dayOfWeekText"]  # Monday as first item in list
    screenWidth = config[
        "screenWidth"
    ]  # Width of E-Ink display. Default is landscape. Need to rotate image to fit.
    screenHeight = config[
        "screenHeight"
    ]  # Height of E-Ink display. Default is landscape. Need to rotate image to fit.
    imageWidth = config["imageWidth"]  # Width of image to be generated for display.
    imageHeight = config["imageHeight"]  # Height of image to be generated for display.
    rotateAngle = config[
        "rotateAngle"
    ]  # If image is rendered in portrait orientation, angle to rotate to fit screen
    calendars = config["calendars"]  # Google calendar ids
    is24hour = config["is24h"]  # set 24 hour time
    calendarsWithLabels = config[
        "calendarsWithLabels"
    ]  # calendar labels to be used in the calendar

    logger, logFile = setup_logger(displayTZ)
    logger.info("Starting daily calendar update")
    logger.info("Run log: {}".format(os.path.abspath(logFile)))

    currDatetime = None

    try:
        # Establish current date and time information
        # Note: For Python datetime.weekday() - Monday = 0, Sunday = 6
        # For this implementation, each week starts on a Sunday and the calendar begins on the nearest elapsed Sunday
        # The calendar will also display 5 weeks of events to cover the upcoming month, ending on a Saturday
        powerService = PowerHelper()
        powerService.sync_time()
        currBatteryLevel = powerService.get_battery()
        logger.info("Battery level at start: {:.3f}".format(currBatteryLevel))

        currDatetime = dt.datetime.now(displayTZ)
        logger.info("Time synchronised to {}".format(currDatetime))
        currDate = currDatetime.date()
        calStartDate = currDate - dt.timedelta(
            days=((currDate.weekday() + (7 - weekStartDay)) % 7)
        )
        calEndDate = calStartDate + dt.timedelta(days=(5 * 7 - 1))
        calStartDatetime = displayTZ.localize(
            dt.datetime.combine(calStartDate, dt.datetime.min.time())
        )
        calEndDatetime = displayTZ.localize(
            dt.datetime.combine(calEndDate, dt.datetime.max.time())
        )

        # Using Google Calendar to retrieve all events within start and end date (inclusive)
        start = dt.datetime.now()
        gcalService = GcalHelper()
        calendarMap = gcalService.retrieve_events(
            calendarsWithLabels,
            calStartDatetime,
            calEndDatetime,
            displayTZ,
            thresholdHours,
        )
        logger.info("Calendar events retrieved in " + str(dt.datetime.now() - start))

        # Populate dictionary with information to be rendered on e-ink display
        calDict = {
            "calendarMap": calendarMap,
            "calStartDate": calStartDate,
            "today": currDate,
            "lastRefresh": currDatetime,
            "batteryLevel": currBatteryLevel,
            "batteryDisplayMode": batteryDisplayMode,
            "dayOfWeekText": dayOfWeekText,
            "weekStartDay": weekStartDay,
            "maxEventsPerDay": maxEventsPerDay,
            "is24hour": is24hour,
        }

        renderService = RenderHelper(imageWidth, imageHeight, rotateAngle)
        calBlackImage, calRedImage = renderService.process_inputs(calDict)

        if isDisplayToScreen:
            from display.display import DisplayHelper

            displayService = DisplayHelper(screenWidth, screenHeight)
            if currDate.weekday() == weekStartDay:
                # calibrate display once a week to prevent ghosting
                displayService.calibrate(cycles=0)  # to calibrate in production
            displayService.update(calBlackImage, calRedImage)
            displayService.sleep()

        currBatteryLevel = powerService.get_battery()
        logger.info("Battery level at end: {:.3f}".format(currBatteryLevel))

    except Exception:
        logger.exception("Daily calendar update failed")

    logger.info("Completed daily calendar update")

    if currDatetime is None:
        logger.error("currDatetime was never set; skipping shutdown check")
    else:
        logger.info(
            "Checking if configured to shutdown safely - Current hour: {}".format(
                currDatetime.hour
            )
        )
    if isShutdownOnComplete and currDatetime is not None:
        if os.environ.get("MAGINKCAL_NO_SHUTDOWN"):
            logger.info("Shutdown skipped (MAGINKCAL_NO_SHUTDOWN is set)")
        elif currDatetime.hour == 8:
            logger.info("Shutting down safely.")
            logging.shutdown()
            os.system("pisugar-poweroff -m 'PiSugar 3'")
            return

    logging.shutdown()

if __name__ == "__main__":
    main()
