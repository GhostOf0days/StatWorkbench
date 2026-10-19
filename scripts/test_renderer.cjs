const fs=require('node:fs');
const path=require('node:path');
const {spawnSync}=require('node:child_process');
const root=path.resolve(__dirname,'..');
const files=fs.readdirSync(path.join(root,'tests')).filter(name=>/^test_.*\.(cjs|mjs)$/.test(name)).sort().map(name=>path.join('tests',name));
if(!files.length)throw new Error('No renderer tests found.');
const run=spawnSync(process.execPath,['--test',...files],{cwd:root,stdio:'inherit'});
if(run.error)throw run.error;
process.exit(run.status??1);
