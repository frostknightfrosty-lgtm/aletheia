const SunCalc=require('/opt/node_modules/suncalc');
const args=process.argv.slice(2);
if(args.length===1 && args[0]==='--health'){console.log('ok');process.exit(0);}
if(args.length!==1){console.error('usage: runner.js <lat,lon[,ISO8601]>');process.exit(2);}
const p=args[0].split(',').map(s=>s.trim()); const lat=Number(p[0]), lon=Number(p[1]);
if(!Number.isFinite(lat)||!Number.isFinite(lon)||lat<-90||lat>90||lon<-180||lon>180){console.error('invalid geolocation');process.exit(2);}
const date=p[2]?new Date(p.slice(2).join(',')):new Date(); if(Number.isNaN(date.getTime())){console.error('invalid timestamp');process.exit(2);}
const pos=SunCalc.getPosition(date,lat,lon); const times=SunCalc.getTimes(date,lat,lon);
const iso={}; for(const [k,v] of Object.entries(times)) iso[k]=v instanceof Date?v.toISOString():v;
console.log(JSON.stringify({timestamp:date.toISOString(),sun_azimuth:pos.azimuth,sun_altitude:pos.altitude,sun_times:iso}));
