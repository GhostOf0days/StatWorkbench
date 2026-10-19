// Convert the original PNG into native icon containers; no design changes.
// Run on macOS; generated platform assets are included in the source release.
const fs=require('node:fs');
const path=require('node:path');
const {spawnSync}=require('node:child_process');
const root=path.resolve(__dirname,'..');
const source=path.join(root,'assets/statworkbench-logo.png');
const folder=path.join(root,'build/statworkbench.iconset');
fs.mkdirSync(folder,{recursive:true});
function run(command,args){const result=spawnSync(command,args,{encoding:'utf8'});if(result.status!==0)throw new Error(result.stderr||result.error?.message||`${command} failed`);}
function resize(size,destination){run('/usr/bin/sips',['-z',String(size),String(size),source,'--out',destination]);}
if(process.platform!=='darwin')throw new Error('Regenerate icons on macOS; committed PNG/ICO/ICNS assets work on all build hosts.');
for(const size of [16,32,128,256,512]){
 resize(size,path.join(folder,`icon_${size}x${size}.png`));
 resize(size*2,path.join(folder,`icon_${size}x${size}@2x.png`));
}
resize(1024,path.join(root,'assets/statworkbench.png'));
// Modern ICNS chunks store their PNG payloads without image re-encoding.
const chunks=[['icp4',16],['icp5',32],['icp6',64],['ic07',128],['ic08',256],['ic09',512],['ic10',1024]].map(([type,size])=>{
 const file=path.join(folder,`mac-${size}.png`);resize(size,file);const bytes=fs.readFileSync(file),header=Buffer.alloc(8);header.write(type,0,4,'ascii');header.writeUInt32BE(bytes.length+8,4);return Buffer.concat([header,bytes]);
});
const icnsHeader=Buffer.alloc(8);icnsHeader.write('icns',0,4,'ascii');icnsHeader.writeUInt32BE(8+chunks.reduce((n,b)=>n+b.length,0),4);
fs.writeFileSync(path.join(root,'assets/statworkbench.icns'),Buffer.concat([icnsHeader,...chunks]));
const images=[16,24,32,48,64,128,256].map(size=>{const file=path.join(folder,`windows-${size}.png`);resize(size,file);return {size,bytes:fs.readFileSync(file)};});
const header=Buffer.alloc(6+16*images.length);header.writeUInt16LE(1,2);header.writeUInt16LE(images.length,4);
let offset=header.length;
images.forEach(({size,bytes},index)=>{const i=6+16*index;header[i]=size===256?0:size;header[i+1]=header[i];header.writeUInt16LE(1,i+4);header.writeUInt16LE(32,i+6);header.writeUInt32LE(bytes.length,i+8);header.writeUInt32LE(offset,i+12);offset+=bytes.length;});
fs.writeFileSync(path.join(root,'assets/statworkbench.ico'),Buffer.concat([header,...images.map(x=>x.bytes)]));
console.log('Created macOS ICNS, Windows ICO and1024px PNG.');
