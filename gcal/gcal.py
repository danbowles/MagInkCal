#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
This is where we retrieve events from the Google Calendar. Before doing so, make sure you have both the
credentials.json and token.pickle in the same folder as this file. If not, run quickstart.py first.
"""

from __future__ import print_function
import datetime as dt
import pickle
import os.path
import pathlib
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
import logging


class GcalHelper:

    def __init__(self):
        self.logger = logging.getLogger('maginkcal')
        # Initialise the Google Calendar using the provided credentials and token
        SCOPES = ['https://www.googleapis.com/auth/calendar.readonly']
        self.currPath = str(pathlib.Path(__file__).parent.absolute())

        creds = None
        # The file token.pickle stores the user's access and refresh tokens, and is
        # created automatically when the authorization flow completes for the first
        # time.
        if os.path.exists(self.currPath + '/token.pickle'):
            with open(self.currPath + '/token.pickle', 'rb') as token:
                creds = pickle.load(token)
        # If there are no (valid) credentials available, let the user log in.
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    self.currPath + '/credentials.json', SCOPES)
                creds = flow.run_local_server(port=0)
            # Save the credentials for the next run
            with open(self.currPath + '/token.pickle', 'wb') as token:
                pickle.dump(creds, token)

        self.service = build('calendar', 'v3', credentials=creds, cache_discovery=False)

    def list_calendars(self):
        # helps to retrieve ID for calendars within the account
        # calendar IDs added to config.json will then be queried for retrieval of events
        self.logger.info('Getting list of calendars')
        calendars_result = self.service.calendarList().list().execute()
        calendars = calendars_result.get('items', [])
        if not calendars:
            self.logger.info('No calendars found.')
        for calendar in calendars:
            summary = calendar['summary']
            cal_id = calendar['id']
            self.logger.info("%s\t%s" % (summary, cal_id))

    def to_datetime(self, isoDatetime, localTZ):
        # replace Z with +00:00 is a workaround until datetime library decides what to do with the Z notation
        toDatetime = dt.datetime.fromisoformat(isoDatetime.replace('Z', '+00:00'))
        return toDatetime.astimezone(localTZ)

    def is_recent_updated(self, updatedTime, thresholdHours):
        # consider events updated within the past X hours as recently updated
        utcnow = dt.datetime.now(dt.timezone.utc)
        diff = (utcnow - updatedTime).total_seconds() / 3600  # get difference in hours
        return diff < thresholdHours

    def adjust_end_time(self, endTime, localTZ):
        # check if end time is at 00:00 of next day, if so set to max time for day before
        if endTime.hour == 0 and endTime.minute == 0 and endTime.second == 0:
            newEndtime = localTZ.localize(
                dt.datetime.combine(endTime.date() - dt.timedelta(days=1), dt.datetime.max.time()))
            return newEndtime
        else:
            return endTime

    def is_multiday(self, start, end):
        # check if event stretches across multiple days
        return start.date() != end.date()

    def retrieve_events(self, calendarsConfig, startDatetime, endDatetime, localTZ, thresholdHours):
        """
        calendar_config: dict of calendarId -> {name, icon}
        Returns: dict of calendarId -> {name, icon, events: [...]}
        """
        self.logger.info(f'Retrieving events between {startDatetime.isoformat()} and {endDatetime.isoformat()}...')

        # Build initial calendar map with empty event lists
        calendar_event_map = {
            cal_id: {**data, "events": []}
            for cal_id, data in calendarsConfig.items()
        }
        
        for cal_id in calendarsConfig:
            try:
                response = self.service.events().list(
                    calendarId=cal_id,
                    timeMin=startDatetime.isoformat(),
                    timeMax=endDatetime.isoformat(),
                    singleEvents=True,
                    orderBy='startTime'
                ).execute()

                events = response.get('items', [])

                for event in events:
                    new_event = {
                        "summary": event.get("summary", ""),
                        "icon": calendarsConfig[cal_id]["icon"],
                        "ownerName": calendarsConfig[cal_id]["name"]
                    }

                    # Handle start datetime
                    if event['start'].get('dateTime'):
                        new_event['allday'] = False
                        new_event['startDatetime'] = self.to_datetime(event['start']['dateTime'], localTZ)
                    else:
                        new_event['allday'] = True
                        new_event['startDatetime'] = self.to_datetime(event['start']['date'], localTZ)

                    # Handle end datetime
                    if event['end'].get('dateTime'):
                        new_event['endDatetime'] = self.adjust_end_time(
                            self.to_datetime(event['end']['dateTime'], localTZ), localTZ)
                    else:
                        new_event['endDatetime'] = self.adjust_end_time(
                            self.to_datetime(event['end']['date'], localTZ), localTZ)

                    new_event['updatedDatetime'] = self.to_datetime(event['updated'], localTZ)
                    new_event['isUpdated'] = self.is_recent_updated(new_event['updatedDatetime'], thresholdHours)
                    new_event['isMultiday'] = self.is_multiday(new_event['startDatetime'], new_event['endDatetime'])

                    calendar_event_map[cal_id]["events"].append(new_event)

            except Exception as e:
                self.logger.warning(f"Failed to fetch events for calendar {cal_id}: {e}")

        return calendar_event_map
        # Call the Google Calendar API and return a list of events that fall within the specified dates
        # eventList = []

        # minTimeStr = startDatetime.isoformat()
        # maxTimeStr = endDatetime.isoformat()
        # if False:
        #     return eventList

        # events_result = []
        # for cal in calendars:
        #     events_result.append(
        #         self.service.events().list(calendarId=cal, timeMin=minTimeStr,
        #                                    timeMax=maxTimeStr, singleEvents=True,
        #                                    orderBy='startTime').execute()
        #     )

        # events = []
        # for eve in events_result:
        #     events += eve.get('items', [])
        #     # events = events_result.get('items', [])

        # if not events:
        #     self.logger.info('No upcoming events found.')
        # for event in events:
        #     # extracting and converting events data into a new list
        #     newEvent = {}
        #     newEvent['summary'] = event['summary']

        #     if event['start'].get('dateTime') is None:
        #         newEvent['allday'] = True
        #         newEvent['startDatetime'] = self.to_datetime(event['start'].get('date'), localTZ)
        #     else:
        #         newEvent['allday'] = False
        #         newEvent['startDatetime'] = self.to_datetime(event['start'].get('dateTime'), localTZ)

        #     if event['end'].get('dateTime') is None:
        #         newEvent['endDatetime'] = self.adjust_end_time(self.to_datetime(event['end'].get('date'), localTZ),
        #                                                        localTZ)
        #     else:
        #         newEvent['endDatetime'] = self.adjust_end_time(self.to_datetime(event['end'].get('dateTime'), localTZ),
        #                                                        localTZ)

        #     newEvent['updatedDatetime'] = self.to_datetime(event['updated'], localTZ)
        #     newEvent['isUpdated'] = self.is_recent_updated(newEvent['updatedDatetime'], thresholdHours)
        #     newEvent['isMultiday'] = self.is_multiday(newEvent['startDatetime'], newEvent['endDatetime'])
        #     eventList.append(newEvent)

        # # We need to sort eventList because the event will be sorted in "calendar order" instead of hours order
        # # TODO: improve because of double cycle for now is not much cost
        # eventList = sorted(eventList, key=lambda k: k['startDatetime'])
        # return eventList
