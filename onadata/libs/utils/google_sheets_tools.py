import httplib2

from apiclient import discovery
from oauth2client.contrib.django_orm import Storage

from django.conf import settings

from onadata.apps.main.models import TokenStorageModel
from onadata.libs.utils.export_tools import (
    ExportBuilder,
    dict_to_joined_export,
    encode_if_str
)
from onadata.libs.utils.common_tags import INDEX, PARENT_INDEX, ID

DISCOVERY_URL = "https://sheets.googleapis.com/$discovery/rest?version=v4"
SHEETS_BASE_URL = 'https://docs.google.com/spreadsheet/ccc?key=%s&hl'
GOOGLE_SHEET_UPLOAD_BATCH = \
    getattr(settings, 'GOOGLE_SHEET_UPLOAD_BATCH', 1000)


def create_service(credentials):
    """
    Create google service which will interact with google api.
    :param credentials:
    :return: Authenticated google service
    """
    http = credentials.authorize(httplib2.Http())
    service = discovery.build('sheets', 'v4', http=http,
                              discoveryServiceUrl=DISCOVERY_URL)
    return service


def create_google_sheet(user, title, xform=None):
    """
    Loads user oauth credential and creates a google sheet with the given
    title.
    :param user:
    :param title:
    :param xform:
    :return: google sheet id
    """
    storage = Storage(TokenStorageModel, 'id', user, 'credential')
    google_credentials = storage.get()

    config = {
        "spreadsheet_title": title,

    }

    google_sheets = GoogleSheetsExportBuilder(xform, google_credentials,
                                              config)
    section_details = google_sheets.create_sheets_n_headers()

    spread_sheet_details = new_spread_sheets(google_sheets.service, title,
                                             section_details)

    return spread_sheet_details.get('spreadsheetId')


def create_drive_folder(credentials, title="onadata"):
    """
    Create a folder in google drive.
    :param credentials:
    :param title: defaults to onadata
    :return: None
    """
    http = httplib2.Http()
    drive = discovery.build("drive", "v3", http=credentials.authorize(http))

    file_metadata = {
        'name': title,
        'mimeType': 'application/vnd.google-apps.folder'
    }

    drive.files().create(body=file_metadata, fields='id').execute()


def get_sheets_folder_id(credentials, folder_name="onadata"):
    """
    Return google drive folder unique id
    :param credentials:
    :param folder_name:
    :return:
    """
    http = httplib2.Http()
    drive = discovery.build("drive", "v3", http=credentials.authorize(http))

    response = drive.files().list(
        q="title = '{}' and trashed = false".format(folder_name)).execute()

    if len(response.get('items')) > 0:
        return response.get('items')[0].get('id')

    return create_drive_folder(credentials, folder_name)


def new_spread_sheets(service, title, sheets_details):
    """
    Creates a new google sheet witj one sheet
    :param service: Authenticated service
    :param title:
    :param sheets_details: List of sheets to be created
    :return:
    """
    sheets = list()
    for sheet in sheets_details:
        sheets.append({
            u'properties':
                {
                    u'title': sheet.get('title'),

                    u'gridProperties':
                        {
                            u'columnCount': len(sheet.get('data')[0]),
                            u'rowCount': 1
                        }

                }
        })

    spread_sheet_details = {
        "properties":  {
            "title": title
        },
        'sheets': sheets
    }

    return service.spreadsheets().create(body=spread_sheet_details).execute()


def get_spread_sheet(service, spread_sheet_id):
    """
    Retrieve google sheet detail
    :param service: Authenticated service
    :param spread_sheet_id:
    :return: dict with google sheet details
    """
    return service.spreadsheets().get(spreadsheetId=spread_sheet_id).execute()


def get_spread_sheet_title(service, spread_sheet_id):
    """
    Returns the current google sheet title
    :param service:
    :param spread_sheet_id:
    :return:
    """
    google_sheet_details = get_spread_sheet(service, spread_sheet_id)

    return google_sheet_details.get('properties').get('title')


def get_spread_sheet_rows(service, spread_sheet_details, row_index=None,
                          sheet_idx=0):
    """
    Retrieve sheet data
    :param service:
    :param spread_sheet_details:
    :param row_index:
    :param sheet_idx:
    :return:
    spread_sheet_details ->

    {
        u'properties':
            {
                u'autoRecalc': u'ON_CHANGE',
                u'defaultFormat':
                {
                    u'backgroundColor':
                    {
                        u'blue': 1, u'green': 1, u'red': 1
                    },
                    u'padding':
                    {
                        u'bottom': 2, u'left': 3, u'right': 3, u'top': 2
                    },
                    u'textFormat':
                    {
                        u'bold': False,
                        u'fontFamily': u'arial,sans,sans-serif',
                        u'fontSize': 10, u'foregroundColor': {},
                        u'italic': False, u'strikethrough': False,
                        u'underline': False
                    },
                    u'verticalAlignment': u'BOTTOM',
                    u'wrapStrategy': u'OVERFLOW_CELL'
                },
                u'locale': u'en_US',
                u'timeZone': u'Asia/Baghdad',
                u'title': u'weka-sync'
            },
            u'sheets':
                [
                    {
                        u'properties':
                            {
                                u'gridProperties':
                                    {
                                        u'columnCount': 41,
                                        u'rowCount': 11
                                    },
                                u'index': 0,
                                u'sheetId': 1836938579,
                                u'sheetType': u'GRID',
                                u'title': u'tom'
                            }
                    }
                ],
        u'spreadsheetId': u'16-58Zf5gDfuKwWFywtMOnJuVN2PTUELjd4Q3yTWAwMA'
    }
    """

    spread_sheet_id = spread_sheet_details.get('spreadsheetId')
    sheet_detail = spread_sheet_details.get('sheets')[sheet_idx]
    grid_properties = sheet_detail.get('properties').get('gridProperties')
    rows = grid_properties.get('rowCount')
    columns = grid_properties.get('columnCount')
    sheet_title = sheet_detail.get('properties').get('title')

    if row_index:
        sheet_range = '{}!A{}:{}{}'.format(sheet_title, row_index,
                                           colnum_string(columns), row_index)
    else:
        sheet_range = '{}!A{}:{}{}'.format(sheet_title, 1,
                                           colnum_string(columns), rows)

    return service.spreadsheets().values()\
        .get(spreadsheetId=spread_sheet_id, range=sheet_range)\
        .execute()


def get_spread_sheet_column(service, spread_sheet_details, column_index=None,
                            sheet_idx=0):
    """
    Return data on a specific column
    :param service:
    :param spread_sheet_details:
    :param column_index:
    :param sheet_idx:
    :return: list of data column
    """
    spread_sheet_id = spread_sheet_details.get('spreadsheetId')
    sheet_detail = spread_sheet_details.get('sheets')[sheet_idx]
    grid_properties = sheet_detail.get('properties').get('gridProperties')
    rows = grid_properties.get('rowCount')
    sheet_title = sheet_detail.get('properties').get('title')

    column_alpha = colnum_string(column_index)

    sheet_range = '{}!{}{}:{}{}'.format(sheet_title, column_alpha, 1,
                                        column_alpha, rows)

    return service.spreadsheets().values() \
        .get(spreadsheetId=spread_sheet_id, range=sheet_range,
             majorDimension="COLUMNS").execute()


def get_spread_sheet_url(spread_sheet_id):
    """
    Generate google sheet url from the spread sheet id
    :param spread_sheet_id:
    :return:
    """
    return SHEETS_BASE_URL % spread_sheet_id


def prepare_row(data, fields):
    """
    creates array of data
    :param data:
    :param fields:
    :return:
    """
    return [encode_if_str(data, f, True) for f in fields]


def set_spread_sheet_data(service, spread_sheet_details,
                          section_details, should_extend=True):
    """
    Upload data to google sheets
    :param service:
    :param spread_sheet_details:
    :param section_details: data to be loadedup
    :param should_extend: if should add a row
    :return:
    """
    details = list()
    sheets = spread_sheet_details.get('sheets')
    spread_sheet_id = spread_sheet_details.get('spreadsheetId')

    for idx, section in enumerate(section_details):
        data = section.get("data")
        rows = len(data)

        if rows > 0:
            if should_extend:
                add_row_or_column(service, spread_sheet_id,
                                  sheets[idx].get('properties').get('sheetId'),
                                  rows=rows)
            details.append(
                {
                    "range": "{}!A{}".format(section.get('title'),
                                             section.get('index')),
                    "majorDimension": "ROWS",
                    "values": data
                })

    payload = {
                "valueInputOption": "USER_ENTERED",
                "data": details
            }

    results = service.spreadsheets().values()\
        .batchUpdate(spreadsheetId=spread_sheet_id, body=payload).execute()

    return results


def add_row_or_column(service, spread_sheet_id, sheet_id, columns=0, rows=1):
    """
    Extends the google sheets according to params provided
    :param service:
    :param spread_sheet_id:
    :param sheet_id:
    :param columns:
    :param rows:
    :return:
    """
    requests = list()

    if columns:
        requests.append({
          "appendDimension": {
            "sheetId": sheet_id,
            "dimension": "COLUMNS",
            "length": columns
          }
        })

    if rows:
        requests.append({
            "appendDimension": {
                "sheetId": sheet_id,
                "dimension": "ROWS",
                "length": rows
            }
        })

    payload = {
      "requests": requests
    }

    return service.spreadsheets()\
        .batchUpdate(spreadsheetId=spread_sheet_id, body=payload).execute()


def delete_row_or_column(service, spread_sheet_id, sheet_id, start_index,
                         end_index, dimension="ROWS"):
    """
    Deletes row or column
    :param service:
    :param spread_sheet_id:
    :param sheet_id:
    :param start_index:
    :param end_index:
    :param dimension:
    :return:
    """
    requests = list()

    requests.append({
        "deleteDimension": {
            "range": {
              "sheetId": sheet_id,
              "dimension": dimension,
              "startIndex": start_index,
              "endIndex": end_index
            }
          }
        })
    payload = {
      "requests": requests
    }

    return service.spreadsheets()\
        .batchUpdate(spreadsheetId=spread_sheet_id, body=payload).execute()


def colnum_string(n):
    """
    Generates excel alpha-numeric label given a column index
    E.g 27 -> AA
    :param n:
    :return:
    """
    div = n
    alpha_numeric = ""
    while div > 0:
        module = (div - 1) % 26
        alpha_numeric = chr(65 + module) + alpha_numeric
        div = int((div - module) / 26)
    return alpha_numeric


def search_rows(service, spread_sheet_details, column, value):
    """
    Search a value on a specific column
    :param service:
    :param spread_sheet_details:
    :param column:
    :param value:
    :return: row index of the found value
    """
    sheets = spread_sheet_details.get('sheets')
    row_index = list()
    for index, d in enumerate(sheets):

        headers_details = get_spread_sheet_rows(service, spread_sheet_details,
                                                row_index=1, sheet_idx=index)
        headers = headers_details.get("values")[0]
        header_index = headers.index(column) + 1

        data_column = get_spread_sheet_column(service, spread_sheet_details,
                                              column_index=header_index,
                                              sheet_idx=index)
        data = data_column.get("values")[0]

        row_index.append(data.index(str(value)) + 1)

    return row_index


def create_sheet_details(sections, row_indexes):
    """
    Creates dict with details about data upload
    :param sections:
    :param row_indexes:
    :return:
    """
    sheets_details = list()
    for idx, section in enumerate(sections):

        sheets_details.append({
            "title": section['name'],
            "data": list(),
            "index": row_indexes[idx]
        })

    return sheets_details


def get_last_data_last_row(spread_sheet_details):
    """
    Returns the last row with data
    :param spread_sheet_details:
    :return:
    """
    sheets = spread_sheet_details.get('sheets')
    last_rows = list()
    for sheet in sheets:
        last_rows.append(sheet.get('properties').get('gridProperties')
                         .get('rowCount'))

    return last_rows


class GoogleSheetsExportBuilder(ExportBuilder):
    """
    Class that handles google sheet export and live syncing
    """
    google_credentials = None
    service = None
    spread_sheet_details = None

    def __init__(self, xform, google_credentials, config={}):
        """
        Constructor
        :param xform:
        :param google_credentials:
        :param config: dict that has spreadsheet title
        """
        self.spreadsheet_title = \
            config.get('spreadsheet_title', xform.id_string)
        self.google_credentials = google_credentials
        self.service = create_service(google_credentials)
        self.set_survey(xform.survey)

    def export(self, data):
        """
        Uploads the data to google sheets and returns download url
        :param data:
        :return:
        """
        sections_details = self.create_sheets_n_headers()

        self.spread_sheet_details = \
            new_spread_sheets(self.service, self.spreadsheet_title,
                              sections_details)
        spread_sheet_id = self.spread_sheet_details.get('spreadsheetId')

        set_spread_sheet_data(self.service, self.spread_sheet_details,
                              sections_details, should_extend=False)
        last_rows = get_last_data_last_row(self.spread_sheet_details)
        row_indexes = map(lambda x: x + 1, last_rows)
        self._insert_data(data, row_indexes)

        self.url = get_spread_sheet_url(spread_sheet_id)

        return self.url

    def create_sheets_n_headers(self):
        sheets_details = list()
        """Writes headers for each section."""
        for section in self.sections:
            section_name = section['name']
            headers = [element['title'] for element in
                       section['elements']] + self.EXTRA_FIELDS

            details = {
                "title": section_name,
                "data": [headers],
                "index": 1
            }
            sheets_details.append(details)

        return sheets_details

    def _insert_data(self, data, row_indexes=[2], new_row=True):
        """Writes data rows for each section."""
        indices = {}
        survey_name = self.survey.name
        batch_size = GOOGLE_SHEET_UPLOAD_BATCH
        processed_data = 0
        sheet_details = create_sheet_details(self.sections, row_indexes)
        for index, d in enumerate(data, 1):
            _id = d.get(ID)
            joined_export = dict_to_joined_export(
                d, index, indices, survey_name, self.survey, d)
            output = ExportBuilder.decode_mongo_encoded_section_names(
                joined_export)
            # attach meta fields (index, parent_index, parent_table)
            # output has keys for every section
            if survey_name not in output:
                output[survey_name] = {}
            output[survey_name][INDEX] = index
            output[survey_name][PARENT_INDEX] = -1
            for idx, section in enumerate(self.sections):
                # get data for this section and write to xls
                section_name = section['name']
                fields = [element['xpath'] for element in
                          section['elements']] + self.EXTRA_FIELDS

                # section might not exist within the output, e.g. data was
                # not provided for said repeat - write test to check this
                row = output.get(section_name, None)
                if type(row) == dict:
                    finalized_rows = prepare_row(
                        self.pre_process_row(row, section), fields)
                    sheet_details[idx].get("data").append(finalized_rows)
                elif type(row) == list:
                    for child_row in row:
                        if not child_row.get(ID):
                            child_row[ID] = _id
                        finalized_rows = prepare_row(
                            self.pre_process_row(child_row, section), fields)
                        sheet_details[idx].get("data").append(finalized_rows)

            if processed_data > batch_size:
                set_spread_sheet_data(self.service, self.spread_sheet_details,
                                      sheet_details, should_extend=new_row)

                self.update_sheet_details()
                row_indexes = get_last_data_last_row(self.spread_sheet_details)
                sheet_details = create_sheet_details(self.sections,
                                                     row_indexes)
                processed_data = 0
            else:
                processed_data += 1

        if processed_data > 0:
            set_spread_sheet_data(self.service, self.spread_sheet_details,
                                  sheet_details, should_extend=new_row)

    def update_sheet_details(self):
        spreadsheet_id = self.spread_sheet_details.get('spreadsheetId')
        self.spread_sheet_details = get_spread_sheet(self.service,
                                                     spreadsheet_id)

    def delete_rows(self, data_id):
        """
        Delete all the rows with the specified data id
        :param data_id:
        :return:
        """
        spreadsheet_id = self.spread_sheet_details.get('spreadsheetId')
        sheets = self.spread_sheet_details.get("sheets")

        for index, sheet in enumerate(sheets):
            sheet_id = sheet.get('properties').get('sheetId')

            headers_details = get_spread_sheet_rows(self.service,
                                                    self.spread_sheet_details,
                                                    row_index=1,
                                                    sheet_idx=index)
            headers = headers_details.get("values")[0]
            header_index = headers.index(ID) + 1

            data_column = get_spread_sheet_column(self.service,
                                                  self.spread_sheet_details,
                                                  column_index=header_index,
                                                  sheet_idx=index)

            data = data_column.get("values")[0]
            delete_row = data.index(str(data_id))
            count_row = data.count(str(data_id))
            last_delete_row = delete_row + count_row

            delete_row_or_column(self.service, spreadsheet_id, sheet_id,
                                 delete_row, last_delete_row)

    def live_update(self, data, spreadsheet_id, delete=False, update=False):
        """
        Keeps google sheet in sync with onadata
        :param data:
        :param spreadsheet_id:
        :param delete: delete the row
        :param update: update already existing row
        :return:
        """

        self.spread_sheet_details = \
            get_spread_sheet(self.service, spreadsheet_id)
        spreadsheet_id = self.spread_sheet_details.get('spreadsheetId')

        if delete:
            return self.delete_rows(data)

        section_details = self.create_sheets_n_headers()

        last_rows = get_last_data_last_row(self.spread_sheet_details)

        # add 1 to all the last row index
        row_indexes = map(lambda x: x + 1, last_rows)
        if update:
            data_id = data[0].get(ID)
            row_indexes = search_rows(self.service, self.spread_sheet_details,
                                      ID, data_id)

        set_spread_sheet_data(self.service, self.spread_sheet_details,
                              section_details, should_extend=False)
        is_new_records = not update
        self._insert_data(data, row_indexes=row_indexes,
                          new_row=is_new_records)

        self.url = get_spread_sheet_url(spreadsheet_id)