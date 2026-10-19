import {defineConfig} from 'vite';
export default defineConfig({root:'renderer',base:'./',build:{outDir:'../renderer-dist',emptyOutDir:true,target:'es2022',chunkSizeWarningLimit:5000},server:{host:'127.0.0.1'}});
