import os
import rasterio
import numpy as np
from datetime import datetime, timedelta
from sentinelhub import (
    SentinelHubRequest, BBox, CRS, MimeType, DataCollection,
    SHConfig
)
from pathlib import Path


def download_clm_mask(bbox, time_interval, config, target_size):
    evalscript_clm = """
    function setup() {
        return {
            input: ["CLM"],
            output: {
                bands: 1,
                sampleType: "FLOAT32"
            }
        };
    }

    function evaluatePixel(sample) {
        return [sample.CLM ? 1.0 : 0.0];
    }
    """
    request = SentinelHubRequest(
        evalscript=evalscript_clm,
        input_data=[SentinelHubRequest.input_data(
            data_collection=DataCollection.SENTINEL2_L1C,
            time_interval=time_interval
        )],
        responses=[SentinelHubRequest.output_response("default", MimeType.TIFF)],
        bbox=bbox,
        size=target_size,
        config=config
    )
    response = request.get_data()
    return np.array(response[0])  # Преобразование ответа в NumPy массив


def download_new_bands(bbox, time_interval, config, target_size, output_dir):
    evalscript_bands = """
    function setup() {
        return {
            input: ["B04", "B08"],
            output: {
                bands: 2,
                sampleType: "FLOAT32"
            }
        };
    }

    function evaluatePixel(sample) {
        return [sample.B04, sample.B08];
    }
    """
    request = SentinelHubRequest(
        evalscript=evalscript_bands,
        input_data=[SentinelHubRequest.input_data(
            data_collection=DataCollection.SENTINEL2_L1C,
            time_interval=time_interval
        )],
        responses=[SentinelHubRequest.output_response("default", MimeType.TIFF)],
        bbox=bbox,
        size=target_size,
        config=config
    )

    os.makedirs(output_dir, exist_ok=True)
    print(f"Save path: {output_dir}")

    response = request.get_data()
    if not response:
        raise ValueError("Empty response received from SentinelHub")

    output_file = os.path.join(output_dir, "bands.tiff")
    with rasterio.open(
            output_file,
            "w",
            driver="GTiff",
            height=target_size[1],
            width=target_size[0],
            count=2,
            dtype=response[0].dtype.name,
            crs=bbox.crs.pyproj_crs(),
            transform=rasterio.transform.from_bounds(*bbox, width=target_size[0], height=target_size[1])
    ) as dst:
        dst.write(response[0][:, :, 0], indexes=1)  # B04
        dst.write(response[0][:, :, 1], indexes=2)  # B08

    print(f"New bands saved to: {output_file}")


def compare_masks(original_mask, candidate_mask, threshold=1.0):
    if original_mask.shape != candidate_mask.shape:
        raise ValueError(f"Размерности масок не совпадают: {original_mask.shape} и {candidate_mask.shape}")
    valid_mask = (~np.isnan(original_mask)) & (~np.isnan(candidate_mask))
    if np.sum(valid_mask) == 0:
        return False
    no_clouds_original = (original_mask[valid_mask] == 0)
    no_clouds_match = (candidate_mask[valid_mask][no_clouds_original] == 0)
    match_ratio = np.sum(no_clouds_match) / np.sum(no_clouds_original)
    return match_ratio >= threshold


def make_config(ins_id):
    config = SHConfig()
    config.sh_client_id = '6ad7a64d-3006-4a1d-9a3e-caeccbce3c04'
    config.sh_client_secret = 'mvOFmvLWFgCOERsxRo4GP1PnKnkH8EU6'
    config.instance_id = ins_id
    return config


if __name__ == "__main__":
    input_dir = r"D:\omela\output_data_sentinel"
    output_base_dir = r"D:\omela\new_band_data"
    config = make_config("6cec2602-3a03-4980-b48a-4d17f8f59bbe")
    start_date = datetime(2023, 5, 2)
    end_date = datetime(2023, 9, 30)

    for folder in os.listdir(input_dir):
        input_path = os.path.join(input_dir, folder)
        if not os.path.isdir(input_path):
            #print(1)
            continue  # Пропускаем файлы
        for name_folder in os.listdir(input_path):
            response_file = os.path.join(input_path, name_folder, 'response.tiff')
            print(response_file)
            if not os.path.exists(response_file):
                print(f"Response file not found in {input_path}, skipping.")
                continue

            try:
                with rasterio.open(response_file) as src:
                    bbox_coords = list(src.bounds)
                    target_bbox = BBox(bbox=bbox_coords, crs=CRS.WGS84)
                    needed_size = [src.width, src.height]
                    old_clm_mask = src.read(4)

                    current_date = start_date
                    while current_date <= end_date:
                        time_interval = (current_date.strftime('%Y-%m-%dT00:00:00Z'),
                                         current_date.strftime('%Y-%m-%dT23:59:59Z'))
                        try:
                            new_mask = download_clm_mask(target_bbox, time_interval, config, needed_size)
                            if compare_masks(old_clm_mask, new_mask, threshold=1):
                                print(f"Masks matched for {current_date.date()} in {folder}, downloading new bands...")
                                output_dir = os.path.join(output_base_dir, folder, name_folder)
                                download_new_bands(target_bbox, time_interval, config, needed_size, output_dir)
                                break
                            else:
                                print(f"Masks do not match for {current_date.date()} in {folder}.")
                        except Exception as e:
                            print(f"Error downloading or processing mask for {current_date.date()} in {folder}: {e}")
                        current_date += timedelta(days=1)
            except Exception as e:
                print(f"Error processing file {response_file} in {folder}: {e}")
