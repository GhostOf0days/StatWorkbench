"""Exercise optional readers in the actual frozen worker using synthetic files."""
from pathlib import Path
import json
import subprocess
import sys
import tempfile
import zipfile
import xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tests.test_optional_formats import fixtures
from tests.test_spjs_project import SpjsProjectTests
from tests.test_report_xlsx import png

def main():
    worker=ROOT/'dist-backend/statworkbench-engine'/('statworkbench-engine.exe' if sys.platform=='win32' else 'statworkbench-engine')
    with tempfile.TemporaryDirectory() as tmp:
        files=fixtures(Path(tmp))
        project=Path(tmp)/'original.spjs'
        document=SpjsProjectTests.document()
        document['workbook']['sheets']['Raw data']['data']['dataTable']['3']={'0':{'formula':'SUM(A2:A3)','value':777}}
        document['workbook']['sheets']['Raw data']['data']['dataTable']['4']={'0':{'formula':'RAND()+A2:A3','value':999,'arrayInfo':{'row':4,'col':0,'rowCount':2,'colCount':2}}}
        project.write_text(json.dumps(document),encoding='utf-8')
        requests=''.join(json.dumps({'id':file.suffix,'method':'import_file','params':{'path':str(file)}})+'\n' for file in files)
        requests+=json.dumps({'id':'.spjs','method':'import_file','params':{'path':str(project)}})+'\n'
        report_path=Path(tmp)/'editable-report.xlsx'
        report={'matrix':[['Report','=1+1'],[1,2]],'chartImages':[
            {'chart':{'type':'scatter','title':'Editable','series':[{'name':'Observed','x':[1,2,3],'y':[2,4,3]}]},'png':png()},
            {'chart':{'type':'histogram','title':'Fallback','series':[{'x':[.5,2],'y':[2,3],'binEdges':[0,1,3]}]},'png':png()},
            {'chart':{'type':'scatter','title':'Custom labels','xTicks':[{'value':1,'label':'First'}],'series':[{'x':[1,2],'y':[3,4]}]},'png':png()},
            {'chart':{'type':'box','title':'Editable box','series':[{'name':'Group','y':[1,2,3],'box':{'q1':1.5,'median':2,'q3':2.5,'low':1,'high':3,'mean':2,'extremeOutliers':[9]}}]},'png':png()},
        ]}
        requests+=json.dumps({'id':'report-xlsx','method':'export_report_xlsx','params':{'path':str(report_path),'report':report}})+'\n'
        run=subprocess.run([str(worker)],input=requests,text=True,capture_output=True,timeout=180,check=True,cwd=ROOT)
        messages=[json.loads(line)for line in run.stdout.splitlines()]
        assert len(messages)==len(files)+2,run.stderr
        for message in messages[:len(files)]:
            assert message['ok'],message
            result=message['result'];assert result['rows']==[[1.5,'A'],[2.5,'B'],[4.0,'A']],message
        message=messages[-2];assert message['ok'],message
        workbook=message['result']['workbook'];sheets=[workbook['sheets'][key] for key in workbook['sheetOrder']]
        assert [sheet['name'] for sheet in sheets]==['Raw data','Report']
        assert sheets[0]['cellData']['3']['0']['f']=='=SUM(A2:A3)'
        assert sheets[0]['cellData']['3']['0']['custom']['statplusImport']['cachedValue']==777
        assert sheets[0]['cellData']['4']['0']['f']=='=SWB.CSE(RAND()+A2:A3,2,2)'
        assert 'f' not in sheets[0]['cellData']['5']['1']
        assert sheets[1]['mergeData']==[{'startRow':0,'endRow':0,'startColumn':0,'endColumn':3}]
        assert sheets[1]['cellData']['2']['1']['s']['n']['pattern']=='0.0000'
        message=messages[-1];assert message['ok'],message
        assert message['result']['nativeCharts']==3 and message['result']['imageCharts']==1,message
        ns={'c':'http://schemas.openxmlformats.org/drawingml/2006/chart','a':'http://schemas.openxmlformats.org/drawingml/2006/main'}
        with zipfile.ZipFile(report_path) as archive:
            chart=ET.fromstring(archive.read('xl/charts/chart1.xml'))
            assert [float(v.text) for v in chart.findall('.//c:xVal/c:numLit/c:pt/c:v',ns)]==[1,2,3]
            assert [float(v.text) for v in chart.findall('.//c:yVal/c:numLit/c:pt/c:v',ns)]==[2,4,3]
            assert not chart.findall('.//c:f',ns)
            custom=ET.fromstring(archive.read('xl/charts/chart2.xml'))
            assert [v.text for v in custom.findall('.//c:dLbl/c:tx/c:rich/a:p/a:r/a:t',ns)]==['First']
            box=ET.fromstring(archive.read('xl/charts/chart3.xml'))
            assert [v.text for v in box.findall('.//c:dLbl/c:tx/c:rich/a:p/a:r/a:t',ns)]==['Group']
            assert any(symbol.get('val')=='star' for symbol in box.findall('.//c:marker/c:symbol',ns))
            assert archive.read('xl/media/image1.png').startswith(b'\x89PNG\r\n\x1a\n')
            relationships=archive.read('xl/drawings/_rels/drawing1.xml.rels').decode()
            assert '/chart' in relationships and '/image' in relationships and 'TargetMode="External"' not in relationships
        result={'verified':True,'formats':[file.suffix for file in files]+['.spjs'],'editableReportXlsx':True,'reportNativeCharts':3,'reportImageCharts':1,'scope':'Nine synthetic numeric/text formats, SPJS layout/formulas, and self-contained OOXML chart literals, custom labels, box outlines and PNG fallback through the frozen worker; this does not exercise an Excel host.'}
        (ROOT/'test-artifacts/frozen-formats-verification.json').write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps(result))
if __name__=='__main__':main()
