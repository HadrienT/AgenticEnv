// usage: node render.mjs out.mp4 | node render.mjs --stills dir t1 t2 ...
import {chromium} from 'playwright-core'
import {spawn} from 'node:child_process'
import {homedir} from 'node:os'
import {fileURLToPath} from 'node:url'
import {dirname,join} from 'node:path'

const here=dirname(fileURLToPath(import.meta.url))
const exe=join(homedir(),'.cache/ms-playwright/chromium-1248/chrome-linux64/chrome')
const FPS=30
const b=await chromium.launch({executablePath:exe,args:['--force-device-scale-factor=1']})
const p=await b.newPage({viewport:{width:1920,height:1080}})
const errs=[];p.on('pageerror',e=>errs.push(e.message));p.on('console',m=>m.type()==='error'&&errs.push(m.text()))
await p.goto('file://'+join(here,'index.html'))
await p.evaluate(()=>document.fonts.ready)
const dur=await p.evaluate(()=>window.DUR)
if(process.argv[2]==='--stills'){
  const[dir,...ts]=process.argv.slice(3)
  for(const t of ts){await p.evaluate(v=>seek(v),+t);await p.screenshot({path:join(dir,`s${t}.png`)})}
}else{
  const ff=spawn('ffmpeg',['-y','-v','error','-f','image2pipe','-c:v','mjpeg','-framerate',FPS,'-i','-','-c:v','libx264','-crf','17','-preset','medium','-pix_fmt','yuv420p','-movflags','+faststart',process.argv[2]],{stdio:['pipe','inherit','inherit']})
  const n=Math.round(dur*FPS)
  for(let i=0;i<n;i++){
    await p.evaluate(v=>seek(v),i/FPS)
    const buf=await p.screenshot({type:'jpeg',quality:96})
    if(!ff.stdin.write(buf))await new Promise(r=>ff.stdin.once('drain',r))
    if(i%120===0)console.log(`${i}/${n}`)
  }
  ff.stdin.end();await new Promise(r=>ff.on('close',r))
}
console.log('errors:',errs.length?errs:'none')
await b.close()
