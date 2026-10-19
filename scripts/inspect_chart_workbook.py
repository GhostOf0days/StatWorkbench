"""Read native chart series from a test workbook exported by a spreadsheet host."""
import json
import sys
import xml.etree.ElementTree as ET
import zipfile

C = "{http://schemas.openxmlformats.org/drawingml/2006/chart}"
A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"


def values(source):
    if source is None:
        return []
    numeric = source.find(".//" + C + "numLit")
    if numeric is None:
        numeric = source.find(".//" + C + "numCache")
    data = numeric
    if data is None:
        data = source.find(".//" + C + "strLit")
    if data is None:
        data = source.find(".//" + C + "strCache")
    if data is None:
        return []
    count = max([int(data.find(C + "ptCount").get("val")), *[int(point.get("idx")) + 1 for point in data.findall(C + "pt")]])
    if not 0 <= count <= 200_000:
        raise ValueError("Chart point inventory exceeds verification bounds.")
    result = [None] * count
    for point in data.findall(C + "pt"):
        value = point.find(C + "v").text or ""
        result[int(point.get("idx"))] = float(value) if numeric is not None else value
    return result


def inspect(path):
    charts = []
    with zipfile.ZipFile(path) as archive:
        for name in sorted(archive.namelist()):
            if not name.startswith("xl/charts/chart") or not name.endswith(".xml"):
                continue
            root = ET.fromstring(archive.read(name))
            title = root.find(".//" + C + "chart/" + C + "title")
            series = []
            for source in root.findall(".//" + C + "ser"):
                label = source.find(C + "tx/" + C + "v")
                if label is None:
                    label = source.find(C + "tx/" + C + "strRef/" + C + "strCache/" + C + "pt/" + C + "v")
                x, y = source.find(C + "xVal"), source.find(C + "yVal")
                if x is None:
                    x = source.find(C + "cat")
                if y is None:
                    y = source.find(C + "val")
                series.append({"name": label.text if label is not None else "", "x": values(x), "y": values(y)})
            charts.append({"title": "".join(node.text or "" for node in title.iter(A + "t")) if title is not None else "", "series": series})
    return charts


if __name__ == "__main__":
    print(json.dumps(inspect(sys.argv[1])))
