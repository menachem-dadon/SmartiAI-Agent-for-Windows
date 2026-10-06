// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { invoke } from "@tauri-apps/api/core";
import { coreApi } from "./coreApi";
import { VoiceOverlayWindow } from "./VoiceOverlayWindow";
vi.mock("@tauri-apps/api/core",()=>({invoke:vi.fn(async()=>{})}));
vi.mock("./coreApi",()=>({coreApi:vi.fn(async()=>({active:true,status:"מקשיב...",error:""}))}));
afterEach(()=>{cleanup();vi.clearAllMocks();vi.unstubAllGlobals();});
test.each(["Escape","button"])("voice overlay renders immediately and cancels using %s",async action=>{
  vi.stubGlobal("matchMedia",()=>({matches:false}));
  render(<VoiceOverlayWindow />);
  expect(screen.getByRole("status").classList.contains("sds-card")).toBe(true);
  expect(screen.getByText("אפשר לדבר עכשיו")).toBeTruthy();
  expect(screen.queryByText(/פותח את סמארטי|מפעיל את סמארטי/)).toBeNull();
  const button=screen.getByRole("button",{name:"בטל האזנה"});
  if(action==="Escape")fireEvent.keyDown(button,{key:"Escape"});else fireEvent.click(button);
  await waitFor(()=>expect(coreApi).toHaveBeenCalledWith("POST","/v2/audio/voice/stop",{},true));
  await waitFor(()=>expect(invoke).toHaveBeenCalledWith("desktop_hide_voice_overlay"));
});
