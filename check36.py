import os

main_path = r"D:\omela\new_band_data"

# Получаем список всех папок в основной директории
folders = [f for f in os.listdir(main_path) if os.path.isdir(os.path.join(main_path, f))]

# Сортируем папки по имени для единообразия
folders_sorted = sorted(folders)

# Проверяем общее количество папок
if len(folders_sorted) != 70:
    print(f"Внимание! Найдено {len(folders_sorted)} папок вместо 70")

# Проверяем каждую папку
for idx, folder in enumerate(folders_sorted, start=1):
    folder_path = os.path.join(main_path, folder)

    try:
        # Получаем список подпапок
        subfolders = [f for f in os.listdir(folder_path)
                      if os.path.isdir(os.path.join(folder_path, f))]

        # Проверяем количество
        if len(subfolders) < 36:
            print(f"Папка #{idx}: '{folder}' содержит только {len(subfolders)} подпапок")

    except PermissionError:
        print(f"Папка #{idx}: '{folder}' - нет доступа")
    except Exception as e:
        print(f"Папка #{idx}: '{folder}' - ошибка: {str(e)}")
