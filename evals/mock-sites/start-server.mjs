import { createServer } from 'vite';
import conf from './vite.config.js';
const server = await createServer({ configFile: false, root: process.cwd(), plugins: conf.plugins, server: conf.server });
await server.listen();
console.log('mock sites ready on :5173');
