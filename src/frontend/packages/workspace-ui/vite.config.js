import {defineConfig} from 'vite';
import react from '@vitejs/plugin-react';
import {fileURLToPath} from 'node:url';
import fs from 'node:fs';
const manifest=JSON.parse(fs.readFileSync(new URL('./package.json',import.meta.url),'utf8'));
const dependencies=[...Object.keys(manifest.dependencies),...Object.keys(manifest.peerDependencies)];
export default defineConfig({plugins:[react()],build:{
 lib:{entry:fileURLToPath(new URL('./src/index.jsx',import.meta.url)),formats:['es'],fileName:'index',cssFileName:'style'},
 rollupOptions:{external:id=>dependencies.some(name=>id===name||id.startsWith(name+'/'))}
}});
