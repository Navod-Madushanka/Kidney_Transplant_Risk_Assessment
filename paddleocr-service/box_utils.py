# paddleocr-service/box_utils.py

def get_box_center(box: list) -> tuple[float, float]:
    x_values = [point[0] for point in box]
    y_values = [point[1] for point in box]

    center_x = sum(x_values) / len(x_values)
    center_y = sum(y_values) / len(y_values)

    return (center_x, center_y)


def group_into_rows(detections: list[dict], y_tolerance: float = 15.0) -> list[list[dict]]:
    detections_with_centers = []
    for detection in detections:
        center_x, center_y = get_box_center(detection["box"])
        detections_with_centers.append(
            {**detection, "center_x": center_x, "center_y": center_y}
        )

    detections_with_centers.sort(key=lambda d: d["center_y"])

    rows: list[list[dict]] = []
    for detection in detections_with_centers:
        placed = False
        for row in rows:
            if abs(row[0]["center_y"] - detection["center_y"]) <= y_tolerance:
                row.append(detection)
                placed = True
                break

        if not placed:
            rows.append([detection])

    for row in rows:
        row.sort(key=lambda d: d["center_x"])

    return rows


def merge_wrapped_lines(rows: list[list[dict]], x_tolerance: float = 40.0) -> list[list[dict]]:
    merged_rows: list[list[dict]] = []

    for row in rows:
        is_short_leftover_row = merged_rows and len(row) < len(merged_rows[-1]) / 2

        if is_short_leftover_row:
            previous_row = merged_rows[-1]
            all_merged = True

            for orphan in row:
                closest_match = min(
                    previous_row, key=lambda d: abs(d["center_x"] - orphan["center_x"])
                )
                x_distance = abs(closest_match["center_x"] - orphan["center_x"])

                if x_distance <= x_tolerance:
                    closest_match["text"] = closest_match["text"] + " " + orphan["text"]
                else:
                    all_merged = False

            if not all_merged:
                merged_rows.append(row)
        else:
            merged_rows.append(row)

    return merged_rows