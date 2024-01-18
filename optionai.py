import requests
import json
import pandas as pd
import dash
from dash import dcc, html
from dash.dependencies import Input, Output, State
import plotly.express as px
from dash.exceptions import PreventUpdate

url_base = 'https://www.nseindia.com/api/option-chain-indices?symbol='

headers = {
    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.4896.127 Safari/537.36'
}

oc_data = {}

app = dash.Dash(__name__)

app.layout = html.Div([
    html.H1("NSE Option Chain Analysis"),

    html.Label("Select Index:"),
    dcc.Dropdown(
        id='index-dropdown',
        options=[
            {'label': 'Nifty', 'value': 'NIFTY'},
            {'label': 'BankNifty', 'value': 'BANKNIFTY'}
        ],
        value= 'NIFTY'  # Default to Nifty
    ),
    html.Label("Select Expiry Date:"),
    dcc.Dropdown(
        id='expiry-dropdown',
        options=[],  # Placeholder for options
        value=None
    ),

    html.Div(id='option-data-display'),
    dcc.Interval(
        id='interval-component',
        interval=60 * 1000,  # in milliseconds, update every 1 minute
        n_intervals=0
    )
])


def create_styled_table(df, highest_oi_index, table_background_color, max_oi_row_color, label=None):
    styles = [
        {
            'if': {'row_index': i},
            'backgroundColor': max_oi_row_color if i == highest_oi_index else 'inherit',
            'color': 'black',
            'border': '2px solid black',
        } for i in range(len(df))
    ]

    if label:
        styles[highest_oi_index].update({'label': label, 'fontWeight': 'bold'})

    return html.Table(
        [html.Tr([html.Th(col) for col in df.columns])] +
        [html.Tr([html.Td(df.iloc[i][col]) for col in df.columns],
                 style=styles[i]) for i in range(len(df))],
        style={'backgroundColor': table_background_color}
    )


def option_activity_type(change_oi, change_price):
    if change_oi > 0 and change_price > 0:
        return "Long Build Up"
    elif change_oi < 0 and change_price < 0:
        return "Long Unwinding"
    elif change_oi > 0 and change_price < 0:
        return "Short Build Up"
    elif change_oi < 0 and change_price > 0:
        return "Short Covering"
    else:
        return "Not Classified"


@app.callback(
    Output('expiry-dropdown', 'options'),
    Output('expiry-dropdown', 'value'),
    Input('index-dropdown', 'value'),
    Input('interval-component', 'n_intervals')
)
def update_options(selected_index, n_intervals):
    url = url_base + selected_index

    response = requests.get(url, headers=headers, timeout=10)
    response_text = response.text
    json_object = json.loads(response_text)

    with open("OC.json", "w") as outfile:
        outfile.write(response_text)

    data = json_object['records']['data']
    e_date = json_object['records']['expiryDates']
    oc_data.clear()

    for ed in e_date:
        oc_data[ed] = {"CE": [], "PE": []}
        for di in range(len(data)):
            if data[di]['expiryDate'] == ed:
                if 'CE' in data[di].keys() and data[di]['CE']['expiryDate'] == ed:
                    oc_data[ed]["CE"].append(data[di]['CE'])
                else:
                    oc_data[ed]["CE"].append('-')

                if 'PE' in data[di].keys() and data[di]['PE']['expiryDate'] == ed:
                    oc_data[ed]["PE"].append(data[di]['PE'])
                else:
                    oc_data[ed]["PE"].append('-')

    options = [{'label': date, 'value': date} for date in e_date]
    value = e_date[0] if e_date else None
    return options, value


@app.callback(
    Output('option-data-display', 'children'),
    Input('index-dropdown', 'value'),
    Input('expiry-dropdown', 'value'),
    prevent_initial_call=True
)
def update_data(selected_index, selected_expiry):
    if not selected_index or not selected_expiry:
        raise PreventUpdate

    url = url_base + selected_index

    response = requests.get(url, headers=headers, timeout=10)
    response_text = response.text
    json_object = json.loads(response_text)

    data = json_object['records']['data']

    ce_data = []
    pe_data = []

    for ce_option, pe_option in zip(oc_data[selected_expiry]["CE"], oc_data[selected_expiry]["PE"]):
        if isinstance(ce_option, dict) and isinstance(pe_option, dict):
            ce_data.append({
                'strike_price': int(ce_option['strikePrice']),
                'open_interest': int(ce_option['openInterest']),
                'change_oi': int(ce_option['changeinOpenInterest']),
                'last_price': float(ce_option['lastPrice']),
                'iv': float(ce_option['impliedVolatility']),
                'activity_type': option_activity_type(int(ce_option['changeinOpenInterest']), float(ce_option['change'])),
            })

            pe_data.append({
                'strike_price': int(pe_option['strikePrice']),
                'open_interest': int(pe_option['openInterest']),
                'change_oi': int(pe_option['changeinOpenInterest']),
                'last_price': float(pe_option['lastPrice']),
                'iv': float(pe_option['impliedVolatility']),
                'activity_type': option_activity_type(int(pe_option['changeinOpenInterest']), float(pe_option['change'])),
            })

    ce_df = pd.DataFrame(ce_data)
    pe_df = pd.DataFrame(pe_data)


    ce_chart = dcc.Graph(
        figure=px.bar(ce_df, x='strike_price', y='open_interest',
                      title='CE Open Interest Comparison', labels={'open_interest': 'Open Interest'},
                      category_orders={"strike_price": sorted(ce_df['strike_price'].unique())},
                      color_discrete_sequence=["blue"], height=400),
        config={'staticPlot': False, 'displayModeBar': True}
    )

    pe_chart = dcc.Graph(
        figure=px.bar(pe_df, x='strike_price', y='open_interest',
                      title='PE Open Interest Comparison', labels={'open_interest': 'Open Interest'},
                      category_orders={"strike_price": sorted(pe_df['strike_price'].unique())},
                      color_discrete_sequence=["green"], height=400),
        config={'staticPlot': False, 'displayModeBar': True}
    )

    ce_pe_comparison_chart = dcc.Graph(
        figure=px.bar(ce_df, x='strike_price', y=['open_interest', 'change_oi'],
                      title='CE Open Interest vs Change in OI', labels={'value': 'Open Interest/Change in OI'},
                      category_orders={"strike_price": sorted(ce_df['strike_price'].unique())},
                      color_discrete_sequence=["blue", "orange"], height=400),
        config={'staticPlot': False, 'displayModeBar': True}
    )

    pe_pe_comparison_chart = dcc.Graph(
        figure=px.bar(pe_df, x='strike_price', y=['open_interest', 'change_oi'],
                      title='PE Open Interest vs Change in OI', labels={'value': 'Open Interest/Change in OI'},
                      category_orders={"strike_price": sorted(pe_df['strike_price'].unique())},
                      color_discrete_sequence=["green", "orange"], height=400),
        config={'staticPlot': False, 'displayModeBar': True}
    )

    ce_table = html.Div([
        html.H3("CE Option Data"),
        create_styled_table(ce_df, ce_df['open_interest'].idxmax(), 'lightcoral', 'red', label="CE")
    ], style={'width': '48%', 'display': 'inline-block', 'float': 'left', 'margin-right': '2%'})

    pe_table = html.Div([
        html.H3("PE Option Data"),
        create_styled_table(pe_df, pe_df['open_interest'].idxmax(), 'lightgreen', 'green', label="PE")
    ], style={'width': '48%', 'display': 'inline-block', 'float': 'left'})

    return [
        html.H3(f"{selected_index} Option Chain Analysis - Expiry Date: {selected_expiry}"),
        html.Div([
            html.Div([
                html.H4("CE Option Data"),
                ce_table
            ], style={'width': '48%', 'display': 'inline-block', 'float': 'left','margin-top': '1600px'}),
            html.Div([
                html.H4("PE Option Data"),
                pe_table
            ], style={'width': '48%', 'display': 'inline-block', 'float': 'right', 'margin-top': '1600px'}),
            # Adjust margin-top as needed
        ]),
        html.Div([
            ce_chart,
            ce_pe_comparison_chart
        ]),
        html.Div([
            pe_chart,
            pe_pe_comparison_chart
        ]),

    ]


if __name__ == '__main__':
    app.run_server(debug=True,host='127.0.0.1', port=8050)
