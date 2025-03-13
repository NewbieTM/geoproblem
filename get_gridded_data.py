import math
import requests 
import datetime
import os
import xarray as xr
import multiprocessing
import matplotlib.pyplot as plt
import tempfile
from matplotlib import cm
import numpy as np
import pandas as pd
import seaborn as sns
from eolearn.core import SaveTask, LoadTask, FeatureType, EOWorkflow,linearly_connect_tasks, EOExecutor,OverwritePermission, EOPatch
from eolearn.io import SentinelHubInputTask, SentinelHubDemTask, SentinelHubEvalscriptTask, get_available_timestamps
from sentinelhub import (
    CRS,
    BBox,
    WmsRequest,
    HistogramType,
    WcsRequest,
    FisRequest,
    Geometry,
    CustomUrlParam,
    DataCollection,
    DownloadRequest,
    MimeType,
    MosaickingOrder,
    SentinelHubDownloadClient,
    SentinelHubRequest,
    bbox_to_dimensions,
    SentinelHubStatistical,
    BBoxSplitter,
    SentinelHubCatalog

)
from pathlib import Path
from datetime import datetime, timedelta
import json
from bs4 import BeautifulSoup

def download_gridded_data(heavy_dir_xml, path_out):
    def parse_file(filename: str):
        if filename.endswith('.xml'):
            with open(filename, 'r') as file:
                content = file.read()
            soup = BeautifulSoup(content, 'xml')
            gr_name = soup.find('Product_Info').find('PRODUCT_URI').text.split('.')[0]
            date_start = soup.find('Product_Info').find('PRODUCT_START_TIME').text
            coordinates_list = list(map(float, soup.find('n1:Geometric_Info').find('EXT_POS_LIST').text.split()))
            coords = [(coordinates_list[i], coordinates_list[i + 1]) for i in range(0, len(coordinates_list), 2)]
            left = min(coord[1] for coord in coords)   # Минимальная долгота
            right = max(coord[1] for coord in coords)  # Максимальная долгота
            bottom = min(coord[0] for coord in coords) # Минимальная широта
            top = max(coord[0] for coord in coords)    # Максимальная широта
        return gr_name, date_start, [left, bottom, right, top]
    data = parse_file(heavy_dir_xml)


    evalscript_all_bands = """
    function setup() {
    return {
        input: [
        {
            bands: [
            "B03", "B04", "B08", "CLM"
            ]
        }
        ],
        output: {
        bands: 4, // 3 спектральных + CLM
        sampleType: "FLOAT32" // Все бэнды сохраняются в одном формате
        }
    };
    }

    function evaluatePixel(sample) {
    return [
        sample.B03, sample.B04, sample.B08, sample.CLM ? 1.0 : 0.0 // CLM в виде бинарного значения
    ];
    }

    """
    bbox = BBox(bbox=data[2], crs=CRS.WGS84)
    granule_id = data[0]

    datetime_str = data[1]
    parsed_time = datetime.strptime(datetime_str, '%Y-%m-%dT%H:%M:%S.%fZ')
    time_interval = (parsed_time - timedelta(hours=1), parsed_time + timedelta(hours=1))
    time_interval_str =  f"{time_interval[0].strftime('%Y-%m-%dT%H:%M:%S.%fZ')}/{time_interval[1].strftime('%Y-%m-%dT%H:%M:%S.%fZ')}"


    def make_config(ins_id):
        config = SHConfig()
        config.sh_client_id = '9caa0952-9941-418e-8cc6-78eed98abe8f'
        config.sh_client_secret = 'k96k8JnL3mC4rNNDv7dsSItf1lntjPQN'
        config.instance_id = ins_id
        return (config)
    from sentinelhub import SHConfig
    config = make_config("8483249a-be2e-4d30-9272-597bcdbdf19e")
    config.save()



    def download_data(bbox, time_interval, size, path_out):
        request = SentinelHubRequest(
        evalscript=evalscript_all_bands,
        input_data=[
            SentinelHubRequest.input_data(
                data_collection=DataCollection.SENTINEL2_L1C,
                time_interval=time_interval
            )
        ],
        responses=[
            SentinelHubRequest.output_response("default", MimeType.TIFF)
        ],
        bbox=bbox,
        size=size,
        config=config,
        data_folder=os.path.join(path_out, Path(heavy_dir_xml).parent.name)
        )
        return request


    catalog = SentinelHubCatalog()
    search_iterator = catalog.search(
        collection="sentinel-2-l1c",
        bbox=bbox, 
        datetime=time_interval_str,
        limit=10
    )
    results = list(search_iterator)
    filtered_results = [result for result in results if granule_id in result["id"]]
    if filtered_results:
        for item in filtered_results:
            print(f"Granule found: {item['id']}")
            print(f"image cloud coverage is {filtered_results[0]['properties']['eo:cloud_cover']}")

    else:
        print("No results found matching the Granule ID.")

    os.mkdir(os.path.join(path_out, Path(heavy_dir_xml).parent.name))
    size = bbox_to_dimensions(bbox, resolution=10)
    print(f"Image shape at {10} m resolution: {size} pixels")
    if size[0] <= 2500 and size[1] <= 2500:
        download_data(bbox, time_interval, size, path_out)
    else:
        a, b = math.ceil(size[0] / 2000), math.ceil(size[1] / 2000)
        print(a, b)
        splitted_data = BBoxSplitter([bbox], CRS.WGS84, (a, b), reduce_bbox_sizes=True)
        bbox_list = splitted_data.get_bbox_list()
        sh_requests = [download_data(sbbox, time_interval, bbox_to_dimensions(sbbox, resolution=10), path_out) for sbbox in bbox_list]
        dl_requests = [request.download_list[0] for request in sh_requests]
        downloaded_data = SentinelHubDownloadClient(config=config).download(dl_requests, max_threads=10)
        data_folder = sh_requests[0].data_folder
        tiffs = [Path(data_folder) / req.get_filename_list()[0] for req in sh_requests]

    splitted_data_info = splitted_data.get_info_list()
    splitted_data_bbox = splitted_data.get_bbox_list()
    for i in range(len(tiffs)):
        fname = tiffs[i].parent.name
        meta = {'bbox': splitted_data_bbox[i].get_geojson(), 
                'index_x': splitted_data_info[i]['index_x'], 
                'index_y': splitted_data_info[i]['index_y']
                }
        os.remove(os.path.join(path_out, Path(heavy_dir_xml).parent.name, fname, 'request.json'))
        with open(os.path.join(path_out, Path(heavy_dir_xml).parent.name, fname, 'meta.json'), 'w') as dst:
            dst.write(json.dumps(meta))



path_in = r"D:\omela\scoltech_150k\src"
path_out = r'D:\omela\output_data_sentinel'

os.makedirs(path_out, exist_ok=True)

for el in os.listdir(path_in)[35:36]:
    xml_path = os.path.join(path_in, el, os.listdir(os.path.join(path_in, el))[0], 'MTD_MSIL1C.xml')
    print(xml_path)

    download_gridded_data(xml_path, path_out)
