#!/usr/bin/env python
#
# Here we are simulating having run a series of fetches from the Harvester and storing the data to csv files.
# These files will be used for building and testing out schema for the newq DB 
#
# We intentionally have time ranges that are overlapping
#
# The filenames are going to have the following nomenclature:
#
# ensemble: An arbitrary string. According to a cursory look at tds, this has values such as:
#    nowcast, nhc0fcl, veerright, etc. So we will set the following defaults:
# grid: hsofs,ec95d,etc
#
#

import os,sys
import pandas as pd
import datetime as dt
import math

from harvester.fetch_station_data import noaanos_fetch_data, contrails_fetch_data, ndbc_fetch_data
from utilities.utilities import utilities as utilities

##
## Some basic functions that will eventually be handled by the caller
##

# Currently supported sources
SOURCES = ['NOAA','CONTRAILS','NDBC']

#def get_noaa_stations(fname='./config/noaa_stations.txt'):
def get_noaa_stations(fname=None):
    """
    Simply read a CSV file containing stations under the header stationid

    Expected format is
        serial_nr, stationid
    """
    if fname is None:
        utilities.log.error('No NOAA station file assigned: Abort')
        sys.exit(1)
    df = pd.read_csv(fname, index_col=0, header=0, skiprows=[1])
    df["stationid"]=df["stationid"].astype(str)
    noaa_stations_list = df["stationid"].to_list() 
    noaa_stations=[word.rstrip() for word in noaa_stations_list] 
    return noaa_stations

def get_contrails_stations(fname=None):
    """
    Simply read a CSV file containing stations under the header stationid
    A convenience method to fetch river guage lists. 
    Contrails data

    Expected format is
        serial_nr, stationid
    """
    if fname is None:
        utilities.log.error('No Contrails station file assigned: Abort')
        sys.exit(1)
    df = pd.read_csv(fname, index_col=0, header=0, skiprows=[1])
    df["stationid"]=df["stationid"].astype(str)
    contrails_stations_list = df["stationid"].to_list()
    contrails_stations=[word.rstrip() for word in contrails_stations_list] 
    return contrails_stations

def get_ndbc_buoys(fname=None):
    """
    Read a list of buo data stations. These data are more complicated because
    the NDBC reader doesnt easily provide the location and state information. Thus
    we expect this input file to carry that infomration.
    
    Expected format is
        serial_nr, stationid, location, state
    
    Return a list of tuples:
    [ (station,location,state), (station, location, state), etc]

    """
    if fname is None:
        utilities.log.error('No NDBC station file assigned: Abort')
        sys.exit(1)
    df_buoys = pd.read_csv(fname,index_col=0, header=0, skiprows=[1])
    df_buoys["stationid"] = df_buoys["stationid"].astype(str)
    # Many buoys have NO STATE affiliation to replace nans with NONE
    df_buoys['state']=df_buoys['state'].fillna('NONE')
    list_stations = df_buoys["stationid"].tolist()
    list_locations = df_buoys["location"].tolist()
    list_states = df_buoys["state"].tolist()
    station_tuples = tuple(zip(list_stations, list_locations, list_states))
    return station_tuples

def choose_common_header_name(product):
    """
    For harvesting, we only want three common data names in the final data time series
    This is complicated by the fact that different sources use different product names. So here
    we manually construct a dictionary of current harvester supported data products

    Input:
        product: (str) input product name

    Return:
        name: (str) selected common name
    """
    product_name_maps={
        'water_level': 'water_level',
        'wave_height': 'wave_height',
        'predictions': 'water_level', 
        'hourly_height': 'water_level',
        'river_water_level': 'water_level',
        'coastal_water_level': 'water_level',
        'air_pressure':'air_pressure',
        'pressure':'pressure',
        'wind_speed':'wind_speed'
        }

    if product in product_name_maps.keys():
        name = product_name_maps[product]
        return name.upper()
    else:
        utilities.log.error('choose_common_header_name. No such product name {}'.format(product))
        sys.exit(1)

def format_data_frames(df, product) -> pd.DataFrame:
    """
    A Common formatting used by all sources
    """
    df.index = df.index.strftime('%Y-%m-%dT%H:%M:%S')
    df.reset_index(inplace=True)
    df_out=pd.melt(df, id_vars=['TIME'])
    df_out.columns=('TIME','STATION',choose_common_header_name(product))
    df_out.set_index('TIME',inplace=True)
    return df_out

##
## End functions
##

##
## Globals
##

dformat='%Y-%m-%d %H:%M:%S'
GLOBAL_TIMEZONE='gmt' # Every source is set or presumed to return times in the zone

#TODO abstract this
#PRODUCT='water_level' # Used by all sources regardless of specifici data product selected
# wave_height
# pressure"
# wind speed"

##
## Run stations
##

def process_noaa_stations(time_range, noaa_stations, interval=None, data_product='water_level', resample_mins=15 ):
    # Fetch the data
    noaa_products=['water_level', 'predictions', 'hourly_height', 'air_pressure', 'wind_speed']
    try:
        if not data_product in noaa_products:
            utilities.log.error('NOAA: data product can only be {}'.format(noaa_products))
            #sys.exit(1)
        noaanos = noaanos_fetch_data(noaa_stations, time_range, product=data_product, interval=interval, resample_mins=resample_mins)
        df_noaa_data = noaanos.aggregate_station_data()
        df_noaa_meta = noaanos.aggregate_station_metadata()
        df_noaa_meta.index.name='STATION'
    except Exception as e:
        utilities.log.error('Error: NOAA: {}'.format(e))
    return df_noaa_data, df_noaa_meta

def process_contrails_stations(time_range, contrails_stations, authentication_config, data_product='river_water_level', resample_mins=15 ):
    # Fetch the data
    contrails_product=['river_water_level','coastal_water_level', 'air_pressure']
    try:
        if data_product not in contrails_product:
            utilities.log.error('Contrails data product can only be: {} was {}'.format(dproduct,data_product))
            #sys.exit(1)
        contrails = contrails_fetch_data(contrails_stations, time_range, authentication_config, product=data_product, owner='NCEM', resample_mins=resample_mins)
        df_contrails_data = contrails.aggregate_station_data()
        df_contrails_meta = contrails.aggregate_station_metadata()
        df_contrails_meta.index.name='STATION'
    except Exception as e:
        utilities.log.error('Error: CONTRAILS: {}'.format(e))
    return df_contrails_data, df_contrails_meta

def process_ndbc_buoys(time_range, ndbc_buoys, data_product='wave_height', resample_mins=15 ):
    # Fetch the data
    ndbc_products=['wave_height', 'air_pressure', 'wind_speed']
    try:
        if not data_product in ndbc_products:
            utilities.log.error('NDBC: data product can only be {}'.format(ndbc_products))
            #sys.exit(1)
        ndbc = ndbc_fetch_data(ndbc_buoys, time_range, product=data_product, resample_mins=resample_mins)
        df_ndbc_data = ndbc.aggregate_station_data()
        df_ndbc_meta = ndbc.aggregate_station_metadata()
        df_ndbc_meta.index.name='STATION'
    except Exception as e:
        utilities.log.error('Error: NEW NDBC: {}'.format(e))
    return df_ndbc_data, df_ndbc_meta

def main(args):
    """
    Generally we anticipate inputting a STOPTIME
    Then the STARTTIME is ndays on the past
    """

    utilities.init_logging(subdir=None, config_file='../config/main.yml')

    if args.sources:
         print('Return list of sources')
         return SOURCES
         sys.exit(0)
    data_source = args.data_source
    data_product = args.data_product

    if data_source.upper() in SOURCES:
        utilities.log.info('Found selected data source {}'.format(data_source))
    else:
        utilities.log.error('Invalid data source {}'.format(data_source))
        sys.exit(1)

    utilities.log.info('Input product {}'.format(data_product))

    # Setup times and ranges
    if args.stoptime is not None:
        time_stop=dt.datetime.strptime(args.stoptime,dformat)
    else:
        time_stop=dt.datetime.now()

    # Do we want a hard starttime?
    if args.starttime is None:
        time_start=time_stop+dt.timedelta(days=args.ndays) # How many days BACK
    else:
        time_start=dt.datetime.strptime(args.starttime,dformat)

    starttime=dt.datetime.strftime(time_start, dformat)
    endtime=dt.datetime.strftime(time_stop, dformat)
    #starttime='2021-12-08 12:00:00'
    #endtime='2021-12-10 00:00:00'

    utilities.log.info('Selected time range is {} to {}, ndays is {}'.format(starttime,endtime,args.ndays))

    # metadata are used to augment filename
    #NOAA/NOS
    if data_source.upper()=='NOAA':
        excludedStations=list()
        time_range=(starttime,endtime) # Can be directly used by NOAA 
        # Use default station list
        noaa_stations=get_noaa_stations(args.station_list) if args.station_list is not None else get_noaa_stations(fname=os.path.join(os.path.dirname(__file__),'../supporting_data','noaa_stations.csv'))
        noaa_metadata='_'+endtime.replace(' ','T') # +'_'+starttime.replace(' ','T')
        data, meta = process_noaa_stations(time_range, noaa_stations, data_product = data_product)
        df_noaa_data = format_data_frames(data, data_product) # Melt the data :s Harvester default format
        # Output
        # If choosing non-default locations BOTH variables must be specified
        try:
            if args.ofile is not None:
                dataf=f'%s/noaa_stationdata%s.csv'% (args.ofile,noaa_metadata)
                metaf=f'%s/noaa_stationdata_meta%s.csv'% (args.ometafile,noaa_metadata)
            else:
                dataf=f'./noaa_stationdata%s.csv'%noaa_metadata
                metaf=f'./noaa_stationdata_meta%s.csv'%noaa_metadata
            df_noaa_data.to_csv(dataf)
            meta.to_csv(metaf)
            utilities.log.info('NOAA data has been stored {},{}'.format(dataf,metaf))
        except Exception as e:
            utilities.log.error('Error: NOAA: Failed Write {}'.format(e))
            sys.exit(1)

    #Contrails
    if data_source.upper()=='CONTRAILS':
        # Load contrails secrets
        conf_name = args.config_name if args.config_name is not None else os.path.join(os.path.dirname(__file__),'../secrets','contrails.yml')
        contrails_config = utilities.load_config(conf_name)['DEFAULT']
        utilities.log.info('Got Contrails access information')
        template = "An exception of type {0} occurred."
        excludedStations=list()
        if data_product=='river_water_level':
            fname='../supporting_data/contrails_stations_rivers.csv'
            meta='_RIVERS'
        else:
            fname='../supporting_data/contrails_stations_coastal.csv'
            meta='_COASTAL'
        try:
            # Build ranges for contrails ( and noaa/nos if you like)
            time_range=(starttime,endtime) 
            # Get default station list
            contrails_stations=get_contrails_stations(args.station_list) if args.station_list is not None else get_contrails_stations(fname)
            contrails_metadata=meta+'_'+endtime.replace(' ','T') # +'_'+starttime.replace(' ','T')
            data, meta = process_contrails_stations(time_range, contrails_stations, contrails_config, data_product = data_product )
            df_contrails_data = format_data_frames(data, data_product) # Melt: Harvester default format
        except Exception as ex:
            utilities.log.error('CONTRAILS error {}, {}'.format(template.format(type(ex).__name__, ex.args)))
            sys.exit(1)
        # If choosing non-default locations BOTH variables must be specified
        try:
            if args.ofile is not None:
                dataf=f'%s/contrails_stationdata%s.csv'% (args.ofile,contrails_metadata)
                metaf=f'%s/contrails_stationdata_meta%s.csv'% (args.ometafile,contrails_metadata)
            else:
                dataf=f'./contrails_stationdata%s.csv'%contrails_metadata
                metaf=f'./contrails_stationdata_meta%s.csv'%contrails_metadata
            df_contrails_data.to_csv(dataf)
            meta.to_csv(metaf)
            utilities.log.info('CONTRAILS data has been stored {},{}'.format(dataf,metaf))
        except Exception as e:
            utilities.log.error('Error: CONTRAILS: Failed Write {}'.format(e))
            sys.exit(1)

    #NDBC
    if data_source.upper()=='NDBC':
        time_range=(starttime,endtime) # Can be directly used by NDBC
        # Use default station list
        ndbc_stations=get_ndbc_buoys(args.station_list) if args.station_list is not None else get_ndbc_buoys(fname=os.path.join(os.path.dirname(__file__),'../supporting_data','ndbc_buoys.csv'))
        ndbc_metadata='_'+endtime.replace(' ','T') # +'_'+starttime.replace(' ','T')
        data, meta  = process_ndbc_buoys(time_range, ndbc_stations, data_product = data_product)
        df_ndbc_data = format_data_frames(data, data_product) # Melt the data :s Harvester default format
        # Output
        # If choosing non-default locations BOTH variables must be specified
        try:
            if args.ofile is not None:
                dataf=f'%s/ndbc_stationdata%s.csv'% (args.ofile,ndbc_metadata)
                metaf=f'%s/ndbc_stationdata_meta%s.csv'% (args.ometafile,ndbc_metadata)
            else:
                dataf=f'./ndbc_stationdata%s.csv'%ndbc_metadata
                metaf=f'./ndbc_stationdata_meta%s.csv'%ndbc_metadata
            df_ndbc_data.to_csv(dataf)
            meta.to_csv(metaf)
            utilities.log.info('NDBC data has been stored {},{}'.format(dataf,metaf))
        except Exception as e:
            utilities.log.error('Error: NDBC: Failed Write {}'.format(e))
            sys.exit(1)


    utilities.log.info('Finished with data source {}'.format(data_source))
    utilities.log.info('Finished')

if __name__ == '__main__':
    from argparse import ArgumentParser
    parser = ArgumentParser()
    parser.add_argument('--ndays', action='store', dest='ndays', default=-2, type=int,
                        help='Number of look-back days from stoptime (or now): default -2')
    parser.add_argument('--stoptime', action='store', dest='stoptime', default=None, type=str,
                        help='Desired stoptime YYYY-mm-dd HH:MM:SS. Default=now')
    parser.add_argument('--starttime', action='store', dest='starttime', default=None, type=str,
                        help='Desired starttime YYYY-mm-dd HH:MM:SS. Default=None')
    parser.add_argument('--sources', action='store_true',
                        help='List currently supported data sources')
    parser.add_argument('--data_source', action='store', dest='data_source', default=None, type=str,
                        help='choose supported data source (case independant) eg NOAA or CONTRAILS')
    parser.add_argument('--data_product', action='store', dest='data_product', default='water_level', type=str,
                        help='choose supported data product eg river_water_level: Only required for Contrails')
    parser.add_argument('--station_list', action='store', dest='station_list', default=None, type=str,
                        help='Choose a non-default location/filename for a stationlist')
    parser.add_argument('--config_name', action='store', dest='config_name', default=None, type=str,
                        help='Choose a non-default contrails auth config_name')
    parser.add_argument('--ofile', action='store', dest='ofile', default=None, type=str,
                        help='Choose a non-default data product output directory')
    parser.add_argument('--ometafile', action='store', dest='ometafile', default=None, type=str,
                        help='Choose a non-default metadata output directory')
    args = parser.parse_args()
    sys.exit(main(args))
