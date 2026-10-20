export type OrbState = 'idle' | 'listening' | 'userSpeaking' | 'smartySpeaking' | 'thinking';
export class SmartyLiveOrb {
 constructor(canvas: HTMLCanvasElement, options?: Record<string, unknown>);
 setState(state: OrbState): void;
 feedAudioLevel(level: number): void;
 destroy(): void;
}
