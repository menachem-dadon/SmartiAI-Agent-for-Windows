import { expect, test } from "vitest";
import { LiveCaptureFilter } from "./liveCapture";
const rate=24000;
const signal=(length:number,frequency:number)=>Float32Array.from({length},(_,i)=>.12*(Math.sin(i*frequency)+.3*Math.sin(i*frequency*1.67)));
test("suppresses delayed playback echo but preserves independent speech mixed into it",()=>{
  const filter=new LiveCaptureFilter(), output=signal(rate,.17);
  filter.record(output,rate,1);
  const offset=2400, echo=output.slice(offset,offset+2048).map(value=>value*.2);
  const end=1+(offset+echo.length)/rate+.08;
  expect(filter.filter(echo,rate,end).every(value=>value===0)).toBe(true);
  const voice=signal(echo.length,.27), mixed=echo.map((value,i)=>value+voice[i]);
  expect(filter.filter(mixed,rate,end)).toBe(mixed);
  const quietVoice=voice.map(value=>value*.05);
  expect(filter.filter(quietVoice,rate,end)).toBe(quietVoice);
});
test("quiet noise becomes equal-length silence and interrupted future audio is not a reference",()=>{
  const filter=new LiveCaptureFilter(), noise=new Float32Array(2048).fill(.0004);
  expect(filter.filter(noise,rate,1)).toEqual(new Float32Array(noise.length));
  const output=signal(rate,.17);filter.record(output,rate,1);filter.truncate(.9);
  const mic=output.slice(2400,4448);
  expect(filter.filter(mic,rate,1+4448/rate+.08)).toBe(mic);
});
