// Live tests require explicit configuration and a disposable CC5 project.
import fs from 'node:fs/promises';
import path from 'node:path';
export const lab = process.env.CC5_LAB_DIR;
export const token = process.env.CC5_BRIDGE_TOKEN;
export const bridgeUrl = process.env.CC5_BRIDGE_URL;
export const frontReference = process.env.CC5_FRONT_REFERENCE;
if (!lab || !path.isAbsolute(lab) || !token || token.length < 32 || !bridgeUrl)
  throw new Error('Set absolute CC5_LAB_DIR, CC5_BRIDGE_TOKEN (32+ characters), and CC5_BRIDGE_URL');
if (process.env.CC5_LIVE_TEST !== '1')
  throw new Error('Open a disposable project and set CC5_LIVE_TEST=1 to allow live test mutations');
await fs.mkdir(lab, {recursive:true});
