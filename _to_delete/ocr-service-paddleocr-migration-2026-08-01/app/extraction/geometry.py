def box_center_y(box: list[int]) -> float:
    return (box[1] + box[3]) / 2

def box_left_x(box: list[int]) -> int:
    return box[0]