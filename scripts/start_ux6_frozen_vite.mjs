// Read-only baseline files; no junction and no second server on the product port.
import { createServer } from '../desktop/node_modules/vite/dist/node/index.js';
import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
const root=resolve(process.argv[2]||'.codex-local/ux-6/frozen-baseline/desktop');
if(!root.startsWith(resolve('.codex-local/ux-6')+'/')&&!root.startsWith(resolve('.codex-local/ux-6')+'\\'))throw Error('QA root required');
const port=Number(process.argv[3]||1447);
if(![1447,1448].includes(port))throw Error('Owned QA port required');
const react=createRequire(new URL('../desktop/package.json',import.meta.url))('@vitejs/plugin-react');
const packages=JSON.parse(readFileSync('desktop/package.json','utf8'));
const alias=Object.keys(packages.dependencies).map(name=>({find:new RegExp('^'+name.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')+'(?=/|$)'),replacement:resolve('desktop/node_modules',name)}));
const server=await createServer({configFile:false,root,plugins:[react()],cacheDir:resolve('.codex-local/ux-6/frozen-cache-'+port),resolve:{alias},server:{host:'127.0.0.1',port,strictPort:true}});
await server.listen();server.printUrls();
