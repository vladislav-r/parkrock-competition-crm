// Keep system numbers and IDs unchanged for lookups and result submission.
export const finalRouteNumber = (number: number) => (number - 1) % 4 + 1;
export const finalRouteName = (number: number, name: string) =>
  /^(Финал|Трасса) [1-8]$/.test(name) ? name.replace(/\d+$/, String(finalRouteNumber(number))) : name;
