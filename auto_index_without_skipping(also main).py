import os
import rasterio
import numpy as np
from rasterio.features import shapes
from shapely.geometry import shape, mapping
import geojson


def find_tiff_files_by_subfolder(directory, target_filename):
    """
    Ищет файлы с заданным именем в подпапках directory и возвращает словарь:
    ключ - относительный путь подпапки относительно directory,
    значение - путь к файлу.
    """
    file_dict = {}
    for root, dirs, files in os.walk(directory):
        for file in files:
            if file == target_filename:
                rel_path = os.path.relpath(root, directory)
                file_dict[rel_path] = os.path.join(root, file)
    return file_dict


def load_bands_from_tiff(file_path):
    """
    Загружает все каналы из .tiff файла.
    :param file_path: Путь к .tiff файлу.
    :return: Список массивов NumPy с данными каждого канала.
    """
    bands_data = []
    with rasterio.open(file_path) as src:
        for i in range(src.count):
            band = src.read(i + 1)
            bands_data.append(band)
    return bands_data


def save_mask_to_geojson(mask, transform, output_file):
    """
    Сохраняет бинарную маску в формате GeoJSON.
    """
    mask = mask.astype(np.uint8)
    shapes_gen = shapes(mask, transform=transform)

    features = []
    for geom, value in shapes_gen:
        if value == 1:
            polygon = shape(geom)
            features.append(geojson.Feature(geometry=mapping(polygon), properties={}))

    geojson_data = geojson.FeatureCollection(features)
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    with open(output_file, 'w') as f:
        geojson.dump(geojson_data, f)
    print(f"Маска успешно сохранена в {output_file}")


# Пути к данным
path_2023 = r"D:\omela\new_band_data"
path_comparison = r"D:\omela\output_data_sentinel"

# Проход по папкам
for folder in os.listdir(path_2023):
    path_to_folder_2023 = os.path.join(path_2023, folder)
    path_to_orig_folder = os.path.join(path_comparison, folder)

    if not os.path.isdir(path_to_folder_2023) or not os.path.isdir(path_to_orig_folder):
        continue

    # Сопоставление подпапок с файлами bands.tiff и response.tiff
    bands_2023_dict = find_tiff_files_by_subfolder(path_to_folder_2023, "bands.tiff")
    response_comp_dict = find_tiff_files_by_subfolder(path_to_orig_folder, "response.tiff")

    common_subfolders = set(bands_2023_dict.keys()) & set(response_comp_dict.keys())

    if not common_subfolders:
        print(f"Нет общих подпапок с файлами в {folder}")
        continue

    for subfolder in common_subfolders:
        bands_path = bands_2023_dict[subfolder]
        response_path = response_comp_dict[subfolder]

        # Определяем путь для маски
        output_dir = os.path.dirname(response_path)
        output_geojson = os.path.join(output_dir, "mask.geojson")

        # Проверяем существование маски
        if os.path.exists(output_geojson):
            print(f"Маска уже существует: {output_geojson}, пропускаем...")
            continue  # Переходим к следующей подпапке

        try:
            # Загрузка бэндов
            bands_2023 = load_bands_from_tiff(bands_path)
            bands_comp = load_bands_from_tiff(response_path)
        except Exception as e:
            print(f"Ошибка загрузки файлов в {subfolder}: {e}")
            continue

        # Проверка количества бэндов
        if len(bands_2023) < 2:
            print(f"Недостаточно бэндов в {bands_path} (требуется 2, найдено {len(bands_2023)})")
            continue
        if len(bands_comp) < 4:
            print(f"Недостаточно бэндов в {response_path} (требуется 4, найдено {len(bands_comp)})")
            continue

        # Извлечение каналов
        B04old = bands_2023[0]
        B08old = bands_2023[1]
        B03 = bands_comp[0]
        B04 = bands_comp[1]
        B08 = bands_comp[2]

        # Расчет индексов
        first_ndvi = (B08old - B04old) / (B08old + B04old + 1e-8)
        second_ndvi = (B08 - B04) / (B08 + B04 + 1e-8)
        ndwi = (B03 - B08) / (B03 + B08 + 1e-8)

        # Создание и сохранение маски
        mask = (ndwi < 0.1) & ((first_ndvi - second_ndvi) > 0.2)
        with rasterio.open(response_path) as src:
            transform = src.transform

        save_mask_to_geojson(mask, transform, output_geojson)
