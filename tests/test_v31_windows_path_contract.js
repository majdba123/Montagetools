const fs=require('fs'),path=require('path'),vm=require('vm');
const src=fs.readFileSync(path.join(__dirname,'../extension/js/main.js'),'utf8');
if(!src.includes("lock.version!=='31.0.9'"))throw new Error('runtime version lock missing');
if(!src.includes('com.hexaterminal.videobuilder.v31_0_1'))throw new Error('bundle lock missing');
if(!src.includes("['-m','hexa_v31.cli'"))throw new Error('module launch missing');
if(!src.includes('normalizeLocalPath'))throw new Error('path normalization missing');
if(src.includes("install_v20.py"))throw new Error('stale installer path in panel');
console.log('V31_WINDOWS_PATH_CONTRACT_PASS');
