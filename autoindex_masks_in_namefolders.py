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


def save_mask_to_geojson(mask, transform, output_file):
    """
    Сохраняет бинарную маску в формате GeoJSON.
    :param mask: Бинарная маска (2D массив).
    :param transform: Трансформация (геопривязка).
    :param output_file: Имя выходного GeoJSON файла.
    """
    mask = mask.astype(np.uint8)  # Преобразуем маску в 0 и 1
    shapes_gen = shapes(mask, transform=transform)

    features = []
    for geom, value in shapes_gen:
        if value == 1:
            polygon = shape(geom)
            features.append(geojson.Feature(geometry=mapping(polygon), properties={}))

    geojson_data = geojson.FeatureCollection(features)
    os.makedirs(os.path.dirname(output_file), exist_ok=True)  # Создаем папку, если она отсутствует
    with open(output_file, 'w') as f:
        geojson.dump(geojson_data, f)

    print(f"Маска успешно сохранена в {output_file}")


# Пути к данным
path_2023 = r"D:\omela\new_band_data"
path_comparison = r"D:\omela\output_data_sentinel"

target_files = ["response.tiff", "bands.tiff"]

# Проход по папкам
for folder in os.listdir(path_2023):
    path_to_folder_2023 = os.path.join(path_2023, folder)
    path_to_orig_folder = os.path.join(path_comparison, folder)

    # Проверяем, существуют ли пути
    if not os.path.isdir(path_to_folder_2023) or not os.path.isdir(path_to_orig_folder):
        continue

    # Поиск файлов
    files_2023 = list_specific_tiff_files(path_to_folder_2023, target_filenames=["bands.tiff"])
    files_comparison = list_specific_tiff_files(path_to_orig_folder, target_filenames=["response.tiff"])

    if not files_2023 or not files_comparison:
        print(f"Файлы TIFF не найдены в папке {folder}")
        continue

    bands_2023 = load_bands_from_tiff(files_2023)
    bands_comparison = load_bands_from_tiff(files_comparison)

    # Разделение каналов
    B04old = [bands_2023[i] for i in range(0, len(bands_2023), 2)]
    B08old = [bands_2023[i] for i in range(1, len(bands_2023), 2)]
    B03 = [bands_comparison[i] for i in range(0, len(bands_comparison), 4)]
    B04 = [bands_comparison[i] for i in range(1, len(bands_comparison), 4)]
    B08 = [bands_comparison[i] for i in range(2, len(bands_comparison), 4)]

    # Расчеты индексов
    first_ndvi_results = [(b08 - b04) / (b08 + b04 + 1e-8) for b04, b08 in zip(B04old, B08old)]
    second_ndvi_results = [(b08 - b04) / (b08 + b04 + 1e-8) for b04, b08 in zip(B04, B08)]
    NDWI = [(b03 - b08) / (b03 + b08 + 1e-8) for b03, b08 in zip(B03, B08)]

    # Создание масок
    masks = [
        ((ndwi < 0.1) & ((first - second) > 0.2))
        for ndwi, first, second in zip(NDWI, first_ndvi_results, second_ndvi_results)
    ]

    # Новая директория для масок
    base_masks_dir = r"D:\omela\masks"

    # Сохранение масок
    for idx, (mask, file_path) in enumerate(zip(masks, files_comparison)):
        with rasterio.open(file_path) as src:
            transform = src.transform
            height, width = src.height, src.width

        reshaped_mask = mask.reshape(height, width)

        # Определяем относительный путь к текущему файлу относительно `path_comparison`
        relative_path = os.path.relpath(file_path, path_comparison)

        # Новый путь для сохранения
        new_path_for_masks = os.path.join(base_masks_dir, os.path.dirname(relative_path))

        # Полный путь к GeoJSON-файлу
        output_geojson_path = os.path.join(new_path_for_masks, f"mask_{idx}.geojson")

        # Сохраняем маску в новом месте
        save_mask_to_geojson(reshaped_mask, transform, output_geojson_path)
