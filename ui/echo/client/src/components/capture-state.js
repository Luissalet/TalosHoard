export function captureState(status) {
  if (status.watching) return { label: "Vigilando", message: "Vigilando el portapapeles." };
  if (status.paused) return { label: "En pausa", message: "Portapapeles en pausa." };
  return { label: "Captura detenida", message: "Pausa retirada. La captura sigue detenida." };
}
