
from math import inf
from .point import Point
import enum

class XP(enum.IntEnum):
    LEFT = 1
    OVERLAP = 2
    RIGHT = 3
class YP(enum.IntEnum):
    BELOW = 1
    OVERLAP = 2
    ABOVE = 3

Directions = enum.IntEnum('Directions', "TOP LEFT BOTTOM RIGHT")

def routeSquare(start_block, finish_block, waypoints):
    def extend_wp(w):
        # Each wp will have one co-ordinate at infinity.
        if abs(w.x) == inf:
            return (Point(x=-inf, y=w.y), Point(x=inf, y=w.y))
        return (Point(x=w.x, y=-inf), Point(x=w.x, y=inf))

    ranges = [(start_block[0], start_block[0] + start_block[1])]
    ranges.extend([extend_wp(wp) for wp in waypoints])
    ranges.append((finish_block[0], finish_block[0] + finish_block[1]))
    centers = [(r[0]+r[1])/2 for r in ranges]

    points = []

    for i, j in zip(range(len(ranges)-1), range(1, len(ranges))):

        current_range, next_range = ranges[i], ranges[j]
        current_center, next_center = centers[i], centers[j]

        # Check if there can be a direct line between the ranges
        xpos = XP.LEFT if next_range[1].x < current_range[0].x else (
            XP.RIGHT if next_range[0].x > current_range[1].x else XP.OVERLAP
        )
        ypos = YP.BELOW if next_range[1].y < current_range[0].y else (
            YP.ABOVE if next_range[0].y > current_range[1].y else YP.OVERLAP
        )

        # Detect a waypoint that runs through the start of finish object
        handled = False
        if i==0:
            if next_range[0].x == -inf and (current_range[0].y <= next_center.y <= current_range[1].y):
                # peek ahead to see which side of the object we need to be
                if centers[j+1].x < current_center.x:
                    points.append(Point(x=current_range[0].x, y=next_center.y))
                else:
                    points.append(Point(x=current_range[1].x, y=next_center.y))
                handled = True
            elif next_range[0].y == -inf and (current_range[0].x <= next_center.x <= current_range[1].x):
                # peek ahead to see which side of the object we need to be
                if centers[j + 1].y < current_center.y:
                    points.append(Point(x=next_center.x, y=current_range[0].y))
                else:
                    points.append(Point(x=next_center.x, y=current_range[1].y))
                handled = True
        if j == len(ranges)-1:
            if current_range[0].x == -inf and (next_range[0].y <= current_center.y <= next_range[1].y):
                # Look behind to see which side of the object we need to be
                if centers[i-1].x < next_center.x:
                    points.append(Point(x=next_range[0].x, y=current_center.y))
                else:
                    points.append(Point(x=next_range[1].x, y=current_center.y))
                handled = True
            elif current_range[0].y == -inf and (next_range[0].x <= current_center.x <= next_range[1].x):
                # look behind to see which side of the object we need to be
                if centers[i- 1].y < next_center.y:
                    points.append(Point(x=current_center.x, y=next_range[0].y))
                else:
                    points.append(Point(x=current_center.x, y=next_range[1].y))
                handled = True

        # Check if a waypoint is connecting to a waypoint
        if (not handled) and current_range[1].x == inf and next_range[1].y == inf:
            handled = True
            points.append(Point(x=next_range[0].x, y=current_range[0].y))
        if (not handled) and current_range[1].y == inf and next_range[1].x == inf:
            handled = True
            points.append(Point(x=current_range[0].x, y=next_range[0].y))
        #Detect situations where there is overlap between objects or waypoints
        if handled:
            pass
        elif ypos == YP.OVERLAP:
            if current_center.x < next_center.x:
                x1 = current_range[1].x
                x2 = next_range[0].x
            else:
                x1 = current_range[0].x
                x2 = next_range[1].x

            # If the whole block is overlapped, draw the line from the center of the smallest
            if current_range[0].y < next_range[0].y:
                if current_range[1].y > next_range[1].y:
                    y = next_center.y
                else:
                    y = (current_range[1].y + next_range[0].y) / 2
            else:
                if current_range[1].y > next_range[1].y:
                    y = (next_range[1].y + current_range[0].y) / 2
                else:
                    y = current_center.y

            points.append(Point(x=x1, y=y))
            points.append(Point(x=x2, y=y))
        elif xpos == XP.OVERLAP:
            # A vertical line
            if current_center.y < next_center.y:
                y1 = current_range[1].y
                y2 = next_range[0].y
            else:
                y1 = current_range[0].y
                y2 = next_range[1].y

            # If the whole block is overlapped, draw the line from the center of the smallest range
            if current_range[0].x < next_range[0].x:
                if current_range[1].x > next_range[1].x:
                    x = next_center.x
                else:
                    x = (current_range[1].x + next_range[0].x) / 2
            else:
                if current_range[1].x > next_range[1].x:
                    x = (next_range[1].x + current_range[0].x) / 2
                else:
                    x = current_center.x


            points.append(Point(x=x, y=y1))
            points.append(Point(x=x, y=y2))
        else:
            # No overlap: draw a line in three parts.
            v = next_center - current_center
            if abs(v.y) > abs(v.x):
                if v.y > 0:
                    quadrant = Directions.TOP
                    start = Point(current_center.x, current_range[1].y)
                    end = Point(next_center.x, next_range[0].y)
                else:
                    quadrant = Directions.BOTTOM
                    start = Point(current_center.x, current_range[0].y)
                    end = Point(next_center.x, next_range[1].y)
            elif v.x > 0:
                quadrant = Directions.RIGHT
                start = Point(current_range[1].x, current_center.y)
                end = Point(next_range[0].x, next_center.y)
            else:
                quadrant = Directions.LEFT
                start = Point(current_range[0].x, current_center.y)
                end = Point(next_range[1].x, next_center.y)

            middle = (start + end) / 2
            if quadrant in [Directions.TOP, Directions.BOTTOM]:
                    p1 = Point(current_center.x, middle.y)
                    p2 = Point(next_center.x, middle.y)
            else:
                    p1 = Point(middle.x, current_center.y)
                    p2 = Point(middle.x, next_center.y)

            points.extend([start, p1, p2, end])
    return points



def testSquareRouter():
    def mkPoints(*args):
        return [Point(x=x, y=y) for x, y in args]

    # Straight horizontal center2center line
    e = mkPoints((200,60), (300,60))
    r = routeSquare(mkPoints((100,40), (100,40)), mkPoints((300,40),(100,40)), [])
    assert e==r, f"Asser error: {r} is not as expected {e}"

    # Straight vertical center2center line
    e = mkPoints((150,80), (150,150))
    r = routeSquare(mkPoints((100,40), (100,40)), mkPoints((100,150),(100,40)), [])
    assert e==r, f"Asser error: {r} is not as expected {e}"

    # Straight horizontal off-center line
    e = mkPoints((200, 65), (300, 65))
    r = routeSquare(mkPoints((100, 40), (100, 40)), mkPoints((300, 50), (100, 40)), [])
    assert e == r, f"Asser error: {r} is not as expected {e}"

    # Straight vertical off-center line
    e = mkPoints((160, 80), (160, 150))
    r = routeSquare(mkPoints((100, 40), (100, 40)), mkPoints((120, 150), (100, 40)), [])
    assert e == r, f"Asser error: {r} is not as expected {e}"

    # Horizontal stepped line
    e = mkPoints((200, 60), (350,60), (350,120), (500,120))
    r = routeSquare(mkPoints((100, 40), (100, 40)), mkPoints((500, 100), (100, 40)), [])
    assert e == r, f"Asser error: {r} is not as expected {e}"

    # Vertical stepped line
    e = mkPoints((150,80), (150,210), (270,210), (270,340))
    r = routeSquare(mkPoints((100, 40), (100, 40)), mkPoints((220, 340), (100, 40)), [])
    assert e == r, f"Asser error: {r} is not as expected {e}"

    # Horizontal by single waypoint above
    e = mkPoints((150,80), (150,100), (350,100), (350,80))
    r = routeSquare(mkPoints((100,40), (100,40)), mkPoints((300,40),(100,40)), mkPoints((inf,100)))
    assert e==r, f"Asser error: {r} is not as expected {e}"

    # Horizontal by single waypoint below
    e = mkPoints((150,40), (150,20), (350,20), (350,40))
    r = routeSquare(mkPoints((100,40), (100,40)), mkPoints((300,40),(100,40)), mkPoints((inf,20)))
    assert e==r, f"Asser error: {r} is not as expected {e}"

    # Vertical by single waypoint to left
    e = mkPoints((200,60), (250,60), (250,170), (200,170))
    r = routeSquare(mkPoints((100,40), (100,40)), mkPoints((100,150),(100,40)), mkPoints((250, inf)))
    assert e==r, f"Asser error: {r} is not as expected {e}"

    # Vertical by single waypoint to right
    e = mkPoints((100,60), (50,60), (50,170), (100,170))
    r = routeSquare(mkPoints((100,40), (100,40)), mkPoints((100,150),(100,40)), mkPoints((50, inf)))
    assert e==r, f"Asser error: {r} is not as expected {e}"

    # A route with two waypoints
    e = mkPoints((200,420), (570,420), (570,100), (350,100), (350,80))
    r = routeSquare(mkPoints((100,400), (100,40)), mkPoints((300,40),(100,40)), mkPoints((570, inf), (inf,100)))
    assert e==r, f"Asser error: {r} is not as expected {e}"

if __name__ == '__main__':
    testSquareRouter()