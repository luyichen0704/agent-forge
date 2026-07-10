/** Demo pacing utilities — realistic delay constants */

export const DELAY = {
  GET_MIN: 150,
  GET_MAX: 350,
  SEND_MESSAGE_MIN: 2200,
  SEND_MESSAGE_MAX: 2900,
  CONFIRM_MIN: 1400,
  CONFIRM_MAX: 1800,
  VOTE: 800,
} as const;

/** Return a random integer in [min, max] */
function rand(min: number, max: number): number {
  return Math.floor(Math.random() * (max - min + 1)) + min;
}

export function sleep(ms: number): Promise<void> {
  return new Promise(resolve => setTimeout(resolve, ms));
}

export function sleepGet(): Promise<void> {
  return sleep(rand(DELAY.GET_MIN, DELAY.GET_MAX));
}

export function sleepSend(): Promise<void> {
  return sleep(rand(DELAY.SEND_MESSAGE_MIN, DELAY.SEND_MESSAGE_MAX));
}

export function sleepConfirm(): Promise<void> {
  return sleep(rand(DELAY.CONFIRM_MIN, DELAY.CONFIRM_MAX));
}

export function sleepVote(): Promise<void> {
  return sleep(DELAY.VOTE);
}
