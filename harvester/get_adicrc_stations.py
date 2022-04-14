#!/usr/bin/env python
#
# Here we bolt the Harvester fetching code into this to facilitate grabbing by our research apps
#
# The get_stations methods for ADCIRC is a list of desired stationIDs. 
# Station ids that do not or no longer exist are quietly ignored.
#
# On input we DO NOT expect a time_range, rather a list of URLS that correspond to the time range.
# This method requires information from both the fort.61 and fort.63 files. So helper methods are 
# included that assume an ASGS format and change the url between fort.61.nc and fort.63.nc and vice verse.
# A list of proper urls can be generated by: generate_urls_from_times.py
#
# Hurricane style URLs are valid and are properly handled by the Harvester fetchers.
#

import  os,sys
import numpy as np
import pandas as pd
import datetime as dt
import netCDF4 as nc4

import harvester.fetch_adcirc_data as fetch_adcirc_data
import harvester.generate_urls_from_times as genurls # generate_urls_from_times

from utilities.utilities import utilities as utilities
from argparse import ArgumentParser

def convert_urls_to_61style(urls):
    """
    Process a list of ASGS urls and mandate filename to be fort.61.nc
    """
    urls_61 = list()
    for url in urls:
        words=url.split('/')
        words[-1]='fort.61.nc'
        urls_61.append('/'.join(words))
    utilities.log.info('Conversion of url list to url_61 list')
    return urls_61

def convert_urls_to_63style(urls):
    """
    Process a list of ASGS urls and mandate filename to be fort.63.nc
    """
    urls_63 = list()
    for url in urls:
        words=url.split('/')
        words[-1]='fort.63.nc'
        urls_63.append('/'.join(words))
    utilities.log.info('Conversion of url list to url_63 list')
    return urls_63

def first_available_netCDF4(urls):
    """
    This method seeks to find the tested netCDF4 in a list of netCDF4 urls.
    So we loop over all and simply test for the exitance of the x variable

    Parameters:
        urls. List of urls to netCDF4 files

    Return:
        url: A single url value
    """
    for url in urls:
        try:
            nc = nc4.Dataset(url)
            gridx = nc.variables['x']
            break
        except OSError: # FileNotFoundError: # OSError:
            # Skip and go onm to the next in the list
            utilities.log.debug('first_true: skip a url look up. Try next iteration')
        except Exception as e:
            utilities.log.debug('first_available_netCDF4: something wrong looking for url: {}'.format(e))
            sys.exit(1)
    return url

#
# A supplementary function. THe Harvesting codes are designed to only fetch station level data. But, for more generalized ADCIRC procesing we also need the
# set of lon(x)/lat(y) coordinates for the given url and grid. These coords can be used, for example, to build offset interpolation surfaces to be used by 
# ADCIRC offset. So we need to call the URL again but for the fort.63.nc file. 

def extract_adcirc_grid_coords( urls_63 )->pd.DataFrame:
    """
    The input URLs is a list. But we only check one of them
    You MUST pass in URLs that point to fort.63.nc

    Parameters:
       urls_63. list(str). THe current list if fort63_style urls from which to get the grid coordinates
    Return:
       adc_coords: Dictionary with the keys ['LON','LAT'] 
    """
    print(urls_63)
    if not isinstance(urls_63, list):
        url=urls_63
    else:
        url=first_available_netCDF4(urls_63) # Assumes all urls are for the same grid
    utilities.log.info("Loading fort.63.log {}".format(url))
    nc = nc4.Dataset(url)
    gridx = nc.variables['x']
    gridy = nc.variables['y']
    adc_coords = {'LON':gridx[:].tolist(),'LAT':gridy[:].tolist()}
    return adc_coords 
##
## Rename ? 
##
class get_adcirc_stations(object):
    """ 
    Class to establish connection to the asgs servers and acquire a WL for the set
    of stations input stations

    Input station IDs must be stationids or tuples of statiods/nodeids) depending on the
    callers choice of fort63_style.

    Parameters: 

    Returns:
        product: ('water_level').
        metadata ('Nometadata'): Applied to all output filenames to create user-tagged names
    """

    # Currently supported sources and products

    SOURCES = ['ASGS']
    ASGS_PRODUCTS = ['water_level']

    def __init__(self, source='ASGS',product='water_level',
                knockout_file=None, fort63_style=False, station_list_file=None):
        """
        get_adcirc_stations constructor

        Parameters: 
            source: str Named source. For now only ASGS
            product: str, product type desired. For now only water_level
            knockout: A dict used to remove ranges of time(s) for a given station
            fort63_style: bool. Perform water level reads on the fort.63 file. Requires a station list
                of tuples that contains stationids, nodeid
   
        """
        self.source = source.upper()

        if self.source not in self.SOURCES:
            utilities.log.error('Indicated source is not available {}, choices {}'.format(self.source,self.SOURCES))
            sys.exit(1)

        selected_products = self.ASGS_PRODUCTS

        # Setup master list of stations. Can override with a list of stationIDs later if you must

        if fort63_style:
            self.station_list=fetch_adcirc_data.get_adcirc_stations_fort63_style(station_list_file)
        else:
            self.station_list=fetch_adcirc_data.get_adcirc_stations_fort61_style(station_list_file)
        utilities.log.info('Fetched station list from {}'.format(self.station_list))

        # Specify the desired products
        self.product = product.lower()
        if self.product not in selected_products:
            utilities.log.error('Requested product not available {}, Possible choices {}'.format(self.product,selected_products)) 
            sys.exit(1)

        # Specify up any knockout filename based exclusions as a Dict()
        if knockout_file is not None:
            self.knockout = utilities.read_json_file(knockout_file)
            utilities.log.info('Value of input knockout file {}'.format(self.knockout_file))
            utilities.log.debug('Values of input knockout dict {}'.format(self.knockout))

        Tmin=None  # These will be populated with the min/max times as a str with format %Y%m%d%H%M
        Tmax=None

        utilities.log.info('SOURCE to fetch from {}'.format(self.source))
        utilities.log.info('PRODUCT to fetch is {}'.format(self.product))

    def remove_knockout_stations(self, df_station) -> pd.DataFrame:
        """
        Input should be a data frame of time indexing and stations as columns.
        The time ranges specified in the args.knockout will be set to Nans inclusively.
        This method can be useful when the indicated statin has historically shown 
        poor unexplained performance over a large window of time
        """
        stations=list(self.knockout.keys()) # How many. We anticipate only one but multiple stations can be handled
        cols=list(map(str,df_station.columns.to_list()))
        # 1 Do any stations exist? If not quietly leave
        if not bool(set(stations).intersection(cols)):
            return df_station
        # 2 Okay for each station loop over time range(s) and NaN away
        utilities.log.debug('Stations is {}'.format(stations))
        utilities.log.debug('dict {}'.format(self.knockout))
        for station in stations:
            for key, value in self.knockout[station].items():
                df_station[station][value[0]:value[1]]=np.nan 
        return df_station

    def override_station_IDs(self, station_list):
        """
        This method allows the user to override the current list of stations to process
        They will be subject to the usual validity testing. We overwrite any station data fetched in the class
    
        Parameters:
            stationlist: list (str) of stationIDs. Overrides any existing list.
        """
        if isinstance(station_list, list):
            self.station_list=station_list
            utility.log.info('Manually resetting value of station_list {}'.format(self.station_list))
        else:
            utility.log.error('Manual station list can only be a list of ids {}'.format(station_list))
            sys.exit(1)

# Choosing a sampling min is non-trivial and depends on the data product selected. Underestimating is better than overestimatating
# Since we will do a rolling averager later followed by a final resampling at 1 hour freq.
# ADCIRC will by default return data back in hourly steps

    def fetch_station_product(self, urls, return_sample_min=0, fort63_style=False):
        """
        Fetch the desire data. The main information is part of the class (sources, products, etc.). However, one must still specify the return_sample_minutes
        to sample the data. The harvesting code will read the raw data for the selected product. Perform an interpolation (it doesn't pad nans), and then
        resample the data at the desired freq (in minutes)

        Parameters:
            urls: List (str). ASGS format. 
            return_sample_min: (int) sampling frequency of the returned, interpolated, data set
        Results:
            data: Sampled data of dims (time x stations)
            meta: associated metadata
        """
        utilities.log.debug('Attempt a product fetch')
        if not isinstance(urls,list):
            utilities.log.warn('Input adcirc url needs to be a list: Try to convert')
            urls=[urls]

        self.instance = fetch_adcirc_data.strip_instance_from_url(urls)# Fix fetch_adcirc_data.py to accept a list 
        self.gridname = fetch_adcirc_data.grab_gridname_from_url(urls) # Fix fetch_adcirc_data.py to accept a list 

        if self.source.upper()=='ASGS':
            adc_stations=self.station_list
            #adc_metadata='_'+endtime.replace(' ','T') 
            adc_metadata = '_TEST_';
            data, meta = fetch_adcirc_data.process_adcirc_stations(urls,adc_stations,self.gridname,self.instance,adc_metadata,data_product=self.product,resample_mins=return_sample_min,fort63_style=fort63_style)

        time_index=data.index.tolist()
        self.Tmin = min(time_index).strftime('%Y%m%d%H')
        self.Tmax = max(time_index).strftime('%Y%m%d%H')
        return data, meta

##
## Example invocation of the main test code
## 

# python get_adicrc_stations.py --url "http://tds.renci.org/thredds/dodsC/2022/nam/2022011600/hsofs/hatteras.renci.org/hsofs-nam-bob-2021/nowcast/fort.63.nc" --instance_name 'hsofs-nam-bob-2021' --data_source 'ASGS' --gridname 'hsofs' --fort63_style

# python get_adicrc_stations.py --url "http://tds.renci.org/thredds/dodsC/2021/al09/11/hsofs/hatteras.renci.org/hsofs-al09-bob/nhcOfcl/fort.61.nc" --instance_name 'hsofs-al09-bob' --data_source 'ASGS' --gridname 'hsofs' --fort63_style

##
## Several scenarios may be used for this example main. For now we choose the ADDA style execution
##
def main(args):
    """
    A simple main method to demonstrate the use of this class
    It assumes the existance of a proper main.yml to get IO information
    It assumes the existance of a proper url_framework.yml which (optionally) can be used to create URLs
    """
    import fetch_adcirc_data as fetch_adcirc_data

    # Basic checks
    if args.config_name is None:
        config_name =os.path.join(os.path.dirname(__file__), '../secrets', 'url_framework.yml')
    else:
        config_name = args.config_name

    if args.url is None and (args.instance_name is None or args.instance_name is None):
        utilities.log.error('Requires value for and grid_name instance_name to build URLs using the YAML methods')
        sys.exit(1)

    # Set up IO env
    utilities.log.info("Product Level Working in {}.".format(os.getcwd()))

    # Set up the times information No need to worry about values for hh:mm:ssZ Subsequent resampling cleans that up
    if args.timeout is None: # Set to a default of now()
        tnow = dt.datetime.now()
        stoptime = tnow.strftime('%Y-%m-%d %H:%M:%S')
    else:
        stoptime=args.timeout
    print('Stoptime and ndays {}. {}'.format(stoptime,args.ndays))

    # Generate a list of URLs consistent with the desired criteria
    # How to do this depends on whether you passed in a template_url or not

    print('Demonstrate URL generation')
    print(args.instance_name)

    # genurls can differentiate between a yaml/url-based approach given status of args.url
    genrpl = genurls.generate_urls_from_times(url=args.url, timeout=stoptime, ndays=args.ndays, grid_name=args.gridname, instance_name=args.instance_name, config_name=config_name)

    if args.url is None:
        urls = genrpl.build_url_list_from_yaml_and_offset( ensemble=args.ensemble_name)
        gridname = args.gridname
    else:
        urls = genrpl.build_url_list_from_template_url_and_offset( ensemble=args.ensemble_name)
        gridname = fetch_adcirc_data.grab_gridname_from_url(urls)
    print(urls)

    # Invoke the harvester related class
    if args.fort63_style:
        urls=convert_urls_to_63style(urls)
    else:
        urls=convert_urls_to_61style(urls)

    # Sample test also needs to have a station list
    station_file = '../supporting_data/CERA_NOAA_HSOFS_stations_V3.1.csv'

    # Run the job
    rpl = get_adcirc_stations(source=args.data_source, product=args.data_product,
                station_list_file=station_file, 
                knockout_file=None, fort63_style=args.fort63_style )

    # Fetch best resolution and no resampling
    data,meta=rpl.fetch_station_product(urls, return_sample_min=args.return_sample_min, fort63_style=args.fort63_style  )

    # Revert Harvester filling of nans to -99999 back to nans
    data.replace('-99999',np.nan,inplace=True)
    meta.replace('-99999',np.nan,inplace=True)

    # Grab the coordinates for the url 
    urls_63 = convert_urls_to_63style(urls)
    adc_coords = extract_adcirc_grid_coords( urls_63 )
    lons = adc_coords['LON']
    lats = adc_coords['LAT']

    print(f'Grid name {genrpl.grid_name}')
    print(f'Instance name {genrpl.instance_name}')

    # Get a last piece of metadata for firsr url in iterable grabs either the time (%Y%m%s%H) or hurricane advisory (int)
    iometadata = '_'+fetch_adcirc_data.strip_time_from_url(urls)
    
    # Write the data to disk in a way that mimics ADDA

    # Write selected in Pickle data 
    metapkl = f'./adc_wl_metadata%s.pkl'%iometadata
    detailedpkl = f'./adc_wl_detailed%s.pkl'%iometadata
    meta.to_pickle(metapkl)
    data.to_pickle(detailedpkl)

    # Write selected in JSON format

    # Convert and write selected JSON data
    #metajson = utilities.writePickle(meta_thresholded.index.strftime('%Y-%m-%d %H:%M:%S'),rootdir=rpl.rootdir,subdir=rpl.iosubdir,fileroot='adc_wl_metadata',iometadata=rpl.iometadata)
    data.index = data.index.strftime('%Y-%m-%d %H:%M:%S')

    metajson = f'./obs_wl_metadata%s.json'%iometadata
    detailedjson = f'./obs_wl_detailed%s.json'%iometadata
    meta.to_json(metapkl)
    data.to_json(detailedpkl)

    # Write out the coords 
    ADCfilecoords = f'./adc_coord%s.json'%iometadata
    pd.DataFrame.from_dict(adc_coords).to_json(ADCfilecoords)
    utilities.log.info('Wrote grid coords to {}'.format(ADCfilecoords))

    print('Finished')

# We need to support both specifying URLs by explicit urls and by specifying time ranges.

if __name__ == '__main__':
    from argparse import ArgumentParser
    parser = ArgumentParser()
    parser.add_argument('--url', action='store', dest='url', default=None, type=str,
                        help='ASGS url to fetch ADCIRC data')
    parser.add_argument('--sources', action='store_true',
                        help='List currently supported data sources')
    parser.add_argument('--data_source', action='store', dest='data_source', default='ASGS', type=str,
                        help='choose supported data source (case independant) eg ASGS')
    parser.add_argument('--data_product', action='store', dest='data_product', default='water_level', type=str,
                        help='choose supported data product eg water_level')
    parser.add_argument('--return_sample_min', action='store', dest='return_sample_min', default=60, type=int,
                        help='return_sample_min is the time stepping in the final data objects. (mins)')
    parser.add_argument('--ndays', default=-2, action='store', dest='ndays',help='Day lag (usually < 0)', type=int)
    parser.add_argument('--timeout', default=None, action='store', dest='timeout', help='YYYY-mm-dd HH:MM:SS. Latest day of analysis def to now()', type=str)
    parser.add_argument('--config_name', action='store', dest='config_name', default=None,
                        help='String: yml config which contains URL structural information')
    parser.add_argument('--instance_name', action='store', dest='instance_name', default=None,
                        help='String: Instance value')
    parser.add_argument('--ensemble_name', action='store', dest='ensemble_name', default='nowcast',
                        help='String: ensemble value')
    parser.add_argument('--fort63_style', action='store_true',
                        help='Boolean: Will inform Harvester to use fort.63.methods to get station nodesids')
    parser.add_argument('--gridname', action='store', dest='gridname', default=None,
                        help='String: Test code gridname value')
    args = parser.parse_args()
    sys.exit(main(args))
