# -*- coding: utf-8 -*-
"""
Учебный проект: "БПЛА с системой распознавания лиц на борту"
Скрипт: Автоматизированный инженерно-технический и экономический расчет параметров
Запуск в терминале: python bpla_face_recognition_calculations.py
"""

from __future__ import annotations
import csv
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

OUTPUT_DIR = Path("results_bpla")
OUTPUT_DIR.mkdir(exist_ok=True)


@dataclass
class CameraParams:
    """
    Класс-контейнер для хранения технических характеристик оптической системы (камеры)
    Все дефолтные значения строго соответствуют Исходным данным (Таблица 4 отчета)
    """
    horizontal_fov_deg: float = 75.0  # угол обзора объектива 
    frame_width_px: int = 4608        
    frame_height_px: int = 2592       
    face_width_m: float = 0.16       
    fps_analysis: float = 10.0       

@dataclass
class BatteryParams:
    """
    Класс-контейнер для хранения параметров аккумуляторной батареи БПЛА
    Данные взяты из электротехнического раздела курсовой работы
    """
    voltage_v: float = 22.2               
    capacity_ah: float = 6.0              
    available_energy_coef: float = 0.8    # разрешено расходовать только 80%
    propulsion_power_w: float = 230.0     

@dataclass
class PayloadPower:
    """
    Класс-контейнер для расчета энергопотребления бортового комплекса распознавания лиц
    Включает в себя все потребители полезной нагрузки в Ваттах (раздел "Энергетический баланс")
    """
    camera_w: float = 3.0      # цифровой оптической камеры
    edge_ai_w: float = 15.0    # ИИ-вычислителя 
    radio_w: float = 2.5       # передатчика телеметрии и сжатого видеопотока
    storage_w: float = 1.2     # твердотельного накопителя для таблиц
    reserve_w: float = 3.0     # резерв мощности

    @property
    def total_w(self) -> float:
        """Динамическое свойство: автоматически возвращает суммарную мощность всей полезной нагрузки"""
        return self.camera_w + self.edge_ai_w + self.radio_w + self.storage_w + self.reserve_w


def write_csv(filename: str, headers: list[str], rows: Iterable[Iterable[object]]) -> None:
    """
    Универсальная служебная функция для записи расчетных данных в файлы CSV.
    Разделителем выбран ';', а кодировкой 'utf-8-sig', чтобы файлы сразу корректно открывались в Excel.
    """
    path = OUTPUT_DIR / filename  
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.writer(file, delimiter=";")  
        writer.writerow(headers)                  
        writer.writerows(rows)                   

def calculate_view_and_gsd(heights_m: list[float], camera: CameraParams) -> list[dict[str, float]]:
    """
    Выполняет геометрический расчет оптических параметров съемки (Полоса обзора и разрешение GSD).
    Реализует формулы из Приложения Б отчета.
    """
    rows = []  
    for height_m in heights_m:
        # W = 2 * H * tg(alpha / 2). Находим ширину захвата камеры на земле в метрах
        width_m = 2 * height_m * math.tan(math.radians(camera.horizontal_fov_deg / 2))
        
        # GSD = W / Nw. Находим размер пикселя на местности (переводим метры в мм умножением на 1000)
        gsd_mm_px = (width_m / camera.frame_width_px) * 1000
        
        # Переводим физический шаг GSD обратно в метры для расчета размера лица на матрице
        gsd_m_px = width_m / camera.frame_width_px
        # Формула: N_face = d_face / GSD. Считаем, сколько пикселей займет лицо шириной 16 см на кадре
        face_px = camera.face_width_m / gsd_m_px
        
        # Упаковываем все вычисленные геометрические параметры текущей высоты в словарь результатов
        rows.append({
            "height_m": height_m,
            "view_width_m": width_m,
            "gsd_mm_px": gsd_mm_px,
            "face_width_px": face_px
        })
    return rows  # Возвращаем итоговый массив расчетов для всех высот полета


def calculate_video_data(camera: CameraParams) -> dict[str, float]:
    """
    Выполняет расчет параметров генерируемого видеопотока и требований к дисковой подсистеме БПЛА.
    Определяет объемы "сырых" кадров и емкость журналов событий.
    """
    # Объем сырого кадра в байтах = Ширина * Высота * 3 канала цвета (Каждый пиксель RGB занимает 3 байта)
    bytes_per_rgb_frame = camera.frame_width_px * camera.frame_height_px * 3
    # Переводим байты в Мегабайты путем деления на 1024 в квадрате (1024 * 1024)
    mb_per_frame = bytes_per_rgb_frame / (1024 ** 2)
    # Поток данных в секунду от сенсора = объем 1 кадра * целевой FPS обработки
    mb_per_second_raw = mb_per_frame * camera.fps_analysis
    
    # Стандартная пропускная способность сжатого видеопотока для передачи по радиоканалу (Мбит/с)
    compressed_stream_mbit_s = 6.0
    # Конвертируем Мегабиты в Мегабайты (1 Байт = 8 Бит), чтобы привести к единым единицам измерения
    compressed_stream_mb_s = compressed_stream_mbit_s / 8
    
    # Расчет размера одного зафиксированного события распознавания (в Мегабайтах):
    # (300 Кб — вырезанное фото лица + 5 Кб — текстовые метаданные + 2 Кб — биометрический дескриптор) / 1000
    event_size_mb = (300.0 + 5.0 + 2.0) / 1000
    # Расчет размера журнала на 1000 событий с учетом коэффициента технического резерва 1.5 (+50%)
    journal_size_mb = 1000 * event_size_mb * 1.5
    
    # Возвращаем собранные данные в виде структурированного словаря параметров памяти
    return {
        "Размер сырого кадра (Мбайт)": mb_per_frame,
        "Сырой поток от камеры (Мбайт/с)": mb_per_second_raw,
        "Сжатый поток радиоканала (Мбит/с)": compressed_stream_mbit_s,
        "Сжатый поток радиоканала (Мбайт/с)": compressed_stream_mb_s,
        "Размер одного события (Мбайт)": event_size_mb,
        "Размер журнала на 1000 событий с резервом (Мбайт)": journal_size_mb
    }


def calculate_processing_performance() -> dict[str, float | bool]:
    """
    Выполняет временной анализ производительности алгоритма распознавания лиц на борту.
    Проверяет, укладывается ли вычислитель в ограничения реального времени (10 кадров/сек).
    """
    # Суммируем время выполнения всех этапов нейросетевого конвейера на 1 кадр (в миллисекундах):
    # 8мс (поиск лиц) + 35мс (выравнивание) + 20мс (экстракция фич) + 5мс (сравнение с базой) + 7мс (запись лога)
    total_ms = 8.0 + 35.0 + 20.0 + 5.0 + 7.0
    # Вычисляем максимальную производительность: делим 1000 миллисекунд (1 секунду) на общее время кадра
    max_fps = 1000 / total_ms
    # Логическая проверка: достаточна ли мощность процессора для удержания целевой планки в 10.0 FPS
    target_is_possible = max_fps >= 10.0
    
    return {
        "total_ms": total_ms,
        "max_fps": max_fps,
        "target_is_possible": target_is_possible
    }


def calculate_energy(battery: BatteryParams, payload: PayloadPower) -> dict[str, float]:
    """
    Рассчитывает энергетический баланс беспилотного летательного аппарата.
    Определяет запасаемую энергию и падение времени полета из-за работы ИИ-комплекса.
    """
    # Полная теоретическая энергия аккумулятора (Ватт-часы) = Напряжение (В) * Емкость (Ач)
    full_energy_wh = battery.voltage_v * battery.capacity_ah
    # Доступная полезная энергия с учетом коэффициента ограничения разряда батареи (обычно 80%)
    available_energy_wh = full_energy_wh * battery.available_energy_coef
    
    # Общая потребляемая мощность системы в полете = Мощность моторов БПЛА + Полная мощность ИИ-нагрузки
    total_power_with_payload_w = battery.propulsion_power_w + payload.total_w
    
    # Расчет полетного времени со включенным распознаванием: Доступная энергия / Суммарная мощность * 60 минут
    flight_time_with_payload_min = (available_energy_wh / total_power_with_payload_w) * 60
    # Расчет базового полетного времени (без ИИ): Доступная энергия / Только мощность моторов * 60 минут
    flight_time_without_payload_min = (available_energy_wh / battery.propulsion_power_w) * 60
    
    # Абсолютное сокращение времени полета дрона в минутах из-за включения полезной нагрузки
    reduction_min = flight_time_without_payload_min - flight_time_with_payload_min
    # Относительное падение автономности полета, выраженное в процентах от базового значения
    reduction_percent = (reduction_min / flight_time_without_payload_min) * 100
    
    return {
        "Полная энергия АКБ (Ватт-час)": full_energy_wh,
        "Доступная энергия АКБ (Ватт-час)": available_energy_wh,
        "Мощность полезной нагрузки общая (Ватт)": payload.total_w,
        "Общее потребление БПЛА в режиме ИИ (Ватт)": total_power_with_payload_w,
        "Время полета без ИИ нагрузки (мин)": flight_time_without_payload_min,
        "Время полета с ИИ нагрузкой (мин)": flight_time_with_payload_min,
        "Сокращение полетного времени (минуты)": reduction_min,
        "Сокращение полетного времени (проценты)": reduction_percent
    }


def calculate_recognition_metrics() -> dict[str, float]:
    """
    Вычисляет ключевые метрики точности и качества работы алгоритма биометрического распознавания.
    Реализует математические формулы оценки точности из Раздела 5 отчета.
    """
    # Формула: FRR = N_fr / N_g. Доля ложных отказов: 6 ошибок распознавания «своих» на 200 честных попыток
    frr = 6 / 200
    # Формула: FAR = N_fa / N_i. Доля ложных совпадений: 2 ошибочных допуска чужаков на 800 попыток проверки
    far = 2 / 800
    # Доля неопределенных результатов («серая зона» уверенности классификатора) на общем объеме в 1000 тестов
    uncertain_rate = 80 / 1000
    # Среднее время задержки выработки окончательного вердикта системой (переводим 1400 мс в секунды)
    avg_delay_s = 1400 / 1000
    
    # Возвращаем результаты, конвертируя коэффициенты ошибок в понятные проценты (умножением на 100)
    return {
        "Коэффициент ложного отказа (FRR, %)": frr * 100,
        "Коэффициент ложного совпадения (FAR, %)": far * 100,
        "Доля сомнительных решений (Требуют оператора, %)": uncertain_rate * 100,
        "Средняя системная задержка ответа (сек)": avg_delay_s
    }


def calculate_risks() -> list[dict[str, object]]:
    """
    Реализует автоматизированную матрицу оценки проектных рисков системы.
    Рассчитывает интегральный уровень опасности каждой угрозы на базе экспертных оценок.
    """
    # Базовый экспертный реестр рисков: [Название риска, Вероятность (1-5), Тяжесть ущерба (1-5), Мера снижения]
    risks = [
        ("Сбой алгоритма при плохом освещении", 3, 4, "Интеграция ИК-подсветки и мультиспектральных камер"),
        ("Перехват управления/данных БПЛА", 2, 5, "Шифрование радиоканала AES-256 и использование ППРЧ"),
        ("Аппаратный отказ вычислителя ИИ в полете", 2, 4, "Сторожевой таймер Watchdog и дублирование контуров навигации"),
        ("Ошибочное совпадение лица (Ложная тревога)", 4, 3, "Обязательная двухэтапная ручная верификация оператором"),
        ("Критическое сокращение времени полета на холоде", 3, 3, "Термоизоляция аккумуляторного отсека и подогрев перед взлетом")
    ]
    
    result = []
    for name, probability, damage, mitigation in risks:
        # Интегральный уровень критичности риска = Вероятность наступления * Тяжесть последствий ущерба
        level = probability * damage
        # Сохраняем расширенную информацию о риске в результирующий список
        result.append({
            "name": name,
            "probability": probability,
            "damage": damage,
            "level": level,
            "mitigation": mitigation
        })
    return result


def main() -> None:
    """
    Главная управляющая функция программы. Координирует вызовы всех расчетных блоков,
    отвечает за красивое форматирование вывода в терминал и сохранение итоговых CSV таблиц.
    """
    # Создаем экземпляры конфигурационных классов с исходными параметрами инженерии
    camera = CameraParams()
    battery = BatteryParams()
    payload = PayloadPower()

    # --- БЛОК 1: Оптическая геометрия и пространственное разрешение (GSD) ---
    print("1. Расчет полосы обзора и GSD")
    # Передаем массив высот полета (10, 15, 20, 25, 30 метров) на расчет
    gsd_rows = calculate_view_and_gsd([10, 15, 20, 25, 30], camera)
    # Построчно печатаем результаты расчетов геометрии с выравниванием колонок текстовой строки
    for row in gsd_rows:
        print(
            f"Высота: {row['height_m']:>2.0f} м | "
            f"Полоса: {row['view_width_m']:.2f} м | "
            f"GSD: {row['gsd_mm_px']:.2f} мм/пикс | "
            f"Лицо: {row['face_width_px']:.0f} пикс"
        )
    # Записываем результаты первого блока расчетов в таблицу "01_gsd.csv"
    write_csv(
        "01_gsd.csv",
        ["Высота, м", "Ширина полосы, м", "GSD, мм/пикс", "Ширина лица, пикс"],
        [[r["height_m"], round(r["view_width_m"], 2), round(r["gsd_mm_px"], 2), round(r["face_width_px"])] for r in gsd_rows],
    )

    # --- БЛОК 2: Анализ параметров видеопотока и систем хранения ---
    print("\n2. Видеопоток и хранение")
    video = calculate_video_data(camera)
    # Выводим в консоль все рассчитанные объемы памяти и потоков
    for key, value in video.items():
        print(f"{key}: {value:.3f}")
    # Сохраняем данные по памяти в таблицу "02_video_storage.csv"
    write_csv("02_video_storage.csv", ["Параметр", "Значение"], [[k, round(v, 4)] for k, v in video.items()])

    # --- БЛОК 3: Временной анализ производительности алгоритма ИИ ---
    print("\n3. Производительность")
    perf = calculate_processing_performance()
    print(f"Итого на кадр: {perf['total_ms']:.0f} мс")
    print(f"Максимальная частота: {perf['max_fps']:.1f} FPS")
    print(f"10 FPS достижимы: {'да' if perf['target_is_possible'] else 'нет'}")
    # Записываем метрики быстродействия в файл "03_performance.csv"
    write_csv(
        "03_performance.csv",
        ["Метрика", "Значение"],
        [
            ["Общее время обработки кадра (мс)", perf["total_ms"]],
            ["Максимально возможный FPS (кадров/сек)", round(perf["max_fps"], 2)],
            ["Выполнение целевого норматива 10 FPS", "Да" if perf["target_is_possible"] else "Нет"]
        ]
    )

    # --- БЛОК 4: Энергетический баланс и автономность полета БПЛА ---
    print("\n4. Энергетический баланс")
    energy = calculate_energy(battery, payload)
    # Показываем энергетические характеристики и падение автономности
    for key, value in energy.items():
        print(f"{key}: {value:.2f}")
    # Сохраняем расчеты энергобаланса в файл "04_energy.csv"
    write_csv("04_energy.csv", ["Показатель энергетики", "Значение"], [[k, round(v, 2)] for k, v in energy.items()])

    # --- БЛОК 5: Расчет точности распознавания (FAR / FRR) ---
    print("\n5. Показатели распознавания")
    metrics = calculate_recognition_metrics()
    for key, value in metrics.items():
        print(f"{key}: {value:.2f}")
    # Экспортируем биометрические метрики в таблицу "05_recognition_metrics.csv"
    write_csv("05_recognition_metrics.csv", ["Метрика точности ИИ", "Значение"], [[k, round(v, 2)] for k, v in metrics.items()])

    # --- БЛОК 6: Расчет интегральных уровней матрицы рисков проекта ---
    print("\n6. Риски")
    risks = calculate_risks()
    # Циклом выводим название угрозы и рассчитанный для нее итоговый балл опасности
    for r in risks:
        print(f"Риск: {r['name'][:35]}... | Критичность: {r['level']:>2} | Мера: {r['mitigation']}")
    # Экспортируем автоматизированную матрицу рисков в таблицу "06_risks_matrix.csv"
    write_csv(
        "06_risks_matrix.csv",
        ["Название риска", "Вероятность (1-5)", "Ущерб (1-5)", "Итоговая критичность", "Мера снижения риска"],
        [[r["name"], r["probability"], r["damage"], r["level"], r["mitigation"]] for r in risks]
    )

    # Выводим уведомление об успешном завершении программы и генерации всех отчетных таблиц
    print(f"\nCSV-файлы сохранены в папку: {OUTPUT_DIR.resolve()}")


# Точка входа в скрипт: запускает функцию main(), только если файл запущен пользователем напрямую
if __name__ == "__main__":
    main()

