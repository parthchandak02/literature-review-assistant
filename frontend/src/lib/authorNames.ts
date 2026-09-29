const INITIALS_RE = /^(?:[A-Z]\.?-?){1,3}$/
const PARTICLES = new Set(["van", "von", "der", "den", "de", "del", "della", "di", "da", "dos", "du", "la", "le", "ten", "ter", "bin", "al", "el"])
const SUFFIXES = new Set(["jr", "jr.", "sr", "sr.", "ii", "iii", "iv", "phd", "md"])
const TITLES = new Set(["dr", "dr.", "prof", "prof.", "mr", "mr.", "mrs", "mrs.", "ms", "ms."])
const VIETNAMESE_FAMILIES = new Set([
  "nguyen", "tran", "le", "pham", "hoang", "huynh", "phan", "vu", "vo", "dang",
  "bui", "do", "ho", "ngo", "duong", "ly", "trinh", "dinh", "truong",
])
const VIETNAMESE_MIDDLES = new Set(["van", "thi", "duc", "minh", "thanh", "ngoc", "quoc", "huu", "thu", "hong"])
const CJK_RE = /[぀-ヿ㐀-鿿가-힯]/

const fold = (t: string) => t.normalize("NFKD").replace(/[̀-ͯ]/g, "").replace(/đ/gi, "d").toLowerCase()
const isInitials = (t: string) => INITIALS_RE.test(t)

function stripAffixes(tokens: string[]): string[] {
  let out = tokens
  while (out.length && TITLES.has(out[0].toLowerCase())) out = out.slice(1)
  while (out.length && SUFFIXES.has(out[out.length - 1].toLowerCase().replace(/,$/, ""))) out = out.slice(0, -1)
  return out
}

/** Family name of one author string; mirrors `src/utils/author_names.py`. */
export function familyName(author: string | null | undefined): string {
  let text = (author ?? "").replace(/\s+/g, " ").trim()
  if (!text) return ""
  if (text.includes(",")) {
    const idx = text.indexOf(",")
    const head = text.slice(0, idx).trim()
    const tail = text.slice(idx + 1).trim()
    text = head
    if (head && !SUFFIXES.has(tail.toLowerCase())) {
      const headTokens = stripAffixes(head.split(" "))
      if (headTokens.length > 1 && !headTokens.slice(1).every(isInitials)) return headTokens.join(" ")
    }
  }
  const tokens = stripAffixes(text.split(" "))
  if (!tokens.length) return ""
  if (tokens.length === 1) return tokens[0]
  if (CJK_RE.test(text)) return tokens[0]
  if (!isInitials(tokens[0]) && tokens.slice(1).every(isInitials)) return tokens[0]
  if (tokens.length >= 3 && VIETNAMESE_FAMILIES.has(fold(tokens[0])) && VIETNAMESE_MIDDLES.has(fold(tokens[1]))) {
    return tokens[0]
  }
  const family = [tokens[tokens.length - 1]]
  for (let i = tokens.length - 2; i >= 1; i--) {
    if (!PARTICLES.has(tokens[i].toLowerCase())) break
    family.unshift(tokens[i])
  }
  return family.join(" ")
}
