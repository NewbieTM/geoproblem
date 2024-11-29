import os
import rasterio
import numpy as np
from rasterio.features import shapes
from shapely.geometry import shape, mapping
import geojson


def list_specific_tiff_files(directory, target_filenames):
    """
    Search for specific .tiff files based on their names in the given directory and its subdirectories.
    :param directory: Root directory to search in.
    :param target_filenames: List of target file names to search for.
    :return: List of full paths to found files.
    """
    tiff_files = []
    for root, _, files in os.walk(directory):
        for file in files:
            if file in target_filenames:
                tiff_files.append(os.path.join(root, file))
    return tiff_files




def load_bands_from_tiff(file_paths):
    """
    Загружает данные всех bands из списка .tiff файлов.
    :param file_paths: Список путей к .tiff файлам.
    :return: Список массивов NumPy с данными каждого файла.
    """
    bands_data = []

    for file_path in file_paths:
        with rasterio.open(file_path) as src:
            for i in range(src.count):
                band = src.read(i + 1)  # Чтение одного канала
                bands_data.append(band)

    return bands_data


path_2023 = r"D:\omela\new_band_data\S2A_MSIL1C_20180611T065621_N0206_R063_T42VUP_20180611T090058.SAFE"
path_comparison = r"D:\omela\output_data_sentinel\S2A_MSIL1C_20180611T065621_N0206_R063_T42VUP_20180611T090058.SAFE"

# Define target filenames to search for
target_files = ["response.tiff", "bands.tiff"]

# Search in the respective directories
files_2023 = list_specific_tiff_files(path_2023, target_filenames=["bands.tiff"])
files_comparison = list_specific_tiff_files(path_comparison, target_filenames=["response.tiff"])

bands_2023 = load_bands_from_tiff(files_2023)
bands_comparison = load_bands_from_tiff(files_comparison)



B04old = [bands_2023[i] for i in range(0, len(bands_2023), 2)]  # Четные индексы
B08old = [bands_2023[i] for i in range(1, len(bands_2023), 2)]
B03 = [bands_comparison[i] for i in range(0, len(bands_comparison), 4)]
B04 = [bands_comparison[i] for i in range(1, len(bands_comparison), 4)]
B08 = [bands_comparison[i] for i in range(2, len(bands_comparison), 4)]


first_ndvi_results = [
    (b08 - b04) / (b08 + b04 + 1e-8)  # + 1e-6 Избегаем деления на ноль, добавляя малую величину
    for b04, b08 in zip(B04old, B08old)
]
second_ndvi_results = [
    (b08 - b04) / (b08 + b04 + 1e-8)  # + 1e-6 Избегаем деления на ноль, добавляя малую величину
    for b04, b08 in zip(B04, B08)
]
NDWI = [
    (b03 - b08) / (b03 + b08 + 1e-8)  # + 1e-6 Избегаем деления на ноль, добавляя малую величину
    for b03, b08 in zip(B03, B08)
]

masks = [
    ((ndwi < 0.2) & ((first - second) > 0.25))
    for ndwi, first, second in zip(NDWI, first_ndvi_results, second_ndvi_results)
]
#print(masks)




# Пример создания GeoJSON из маски
def save_mask_to_geojson(mask, transform, output_file):
    """
    Сохраняет бинарную маску в формате GeoJSON.
    :param mask: Бинарная маска (2D массив).
    :param transform: Трансформация (геопривязка).
    :param output_file: Имя выходного GeoJSON файла.
    """
    mask = mask.astype(np.uint8)  # Преобразуем маску в 0 и 1

    # Генерация геометрии полигонов из маски
    shapes_gen = shapes(mask, transform=transform)

    features = []
    for geom, value in shapes_gen:
        if value == 1:  # Используем только маску с меткой "1"
            polygon = shape(geom)
            features.append(geojson.Feature(geometry=mapping(polygon), properties={}))

    # Запись в GeoJSON файл
    geojson_data = geojson.FeatureCollection(features)
    with open(output_file, 'w') as f:
        geojson.dump(geojson_data, f)

    print(f"Маска успешно сохранена в {output_file}")



for idx, (mask, file_path) in enumerate(zip(masks, files_comparison)):
    with rasterio.open(file_path) as src:
        transform = src.transform  # Извлекаем трансформацию из текущего TIFF
        height, width = src.height, src.width  # Размеры для проверки формы маски

    # Убеждаемся, что размер маски соответствует TIFF
    reshaped_mask = mask.reshape(height, width)

    # Имя выходного GeoJSON файла
    output_geojson_path = f"mask_{idx + 1}.geojson"

    # Сохранение текущей маски в GeoJSON
    save_mask_to_geojson(reshaped_mask, transform, output_geojson_path)
