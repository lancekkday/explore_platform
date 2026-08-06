// device_id 等長 ID 的統一截斷顯示(完整值放 title/hover)。
// 超過 n 碼才加省略號,避免短 ID 也掛個「…」誤導成有被截斷。
export function truncId(id, n = 8) {
  if (!id) return ''
  return id.length > n ? `${id.slice(0, n)}…` : id
}
