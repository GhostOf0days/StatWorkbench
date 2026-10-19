#!/usr/bin/env python3
"""Generate the optional Excel ribbon from the desktop engine's actual catalog."""
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.worker import dispatch


def ribbon_xml():
    names = json.loads((ROOT / 'electron/procedures.json').read_text()) + json.loads((ROOT / 'electron/extension-procedures.json').read_text())
    catalog = {p['id']: p for p in dispatch('catalog', {})}
    if set(catalog) != {p['id'] for p in names}:
        raise ValueError('Desktop names and engine procedure IDs differ.')
    root = ET.Element('customUI', xmlns='http://schemas.microsoft.com/office/2006/01/customui')
    tab = ET.SubElement(ET.SubElement(ET.SubElement(root, 'ribbon'), 'tabs'), 'tab', id='StatWorkbenchTab', label='StatWorkbench')
    launch = ET.SubElement(tab, 'group', id='StatWorkbenchLaunch', label='Workbook')
    ET.SubElement(launch, 'button', id='StatWorkbenchOpen', label='Open StatWorkbench', imageMso='FileOpen', onAction='OnAction', tag='open')
    ET.SubElement(launch, 'button', id='StatWorkbenchPreferences', label='Preferences', onAction='OnAction', tag='preferences')
    group = ET.SubElement(tab, 'group', id='StatWorkbenchStatistics', label='Analyze selected cells')
    menus = {}
    for entry in names:
        category = catalog[entry['id']]['category']
        if category not in menus:
            menus[category] = ET.SubElement(group, 'menu', id='StatWorkbenchCategory' + str(len(menus)), label=category)
        ET.SubElement(menus[category], 'button', id='StatWorkbenchAnalysis' + entry['id'].replace('.', '_'), label=entry['name'] + '…', onAction='OnAction', tag='analysis:' + entry['id'])
    ET.indent(root, space='  ')
    return ET.tostring(root, encoding='unicode', xml_declaration=False) + '\n'


if __name__ == '__main__':
    target = ROOT / 'addin/windows/Ribbon.xml'
    text = ribbon_xml()
    if '--check' in sys.argv:
        if not target.exists() or target.read_text() != text:
            raise SystemExit('Excel ribbon is stale. Run scripts/generate_excel_ribbon.py.')
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)
    print('Excel ribbon matches all desktop analysis commands.')
