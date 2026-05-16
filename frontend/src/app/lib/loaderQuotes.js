/**
 * Loader quote bank — investor wisdom shown under the Mission Control and
 * News Wire loaders while heavy work runs.
 *
 * Curation principles:
 *   • Patience / long-term mindset (the opposite of day-trading slop)
 *   • Names users recognize → Buffett, Munger, Lynch, Bogle, Templeton,
 *     Graham, Keynes — credibility-anchored
 *   • Concise (under 120 chars) so they fit on one line on mobile
 *   • Educational, not advisory — fits our SEBI-unregistered compliance posture
 *
 * Anything ambiguously attributed (Einstein on compound interest, etc.) is
 * deliberately left out — better to ship 20 verified than 40 mixed.
 */

export const LOADER_QUOTES = [
  {
    text: "The stock market is a device for transferring money from the impatient to the patient.",
    author: "Warren Buffett",
  },
  {
    text: "The big money is not in the buying and selling, but in the waiting.",
    author: "Charlie Munger",
  },
  {
    text: "Time in the market beats timing the market.",
    author: "Investing maxim",
  },
  {
    text: "Know what you own, and know why you own it.",
    author: "Peter Lynch",
  },
  {
    text: "Be fearful when others are greedy, and greedy when others are fearful.",
    author: "Warren Buffett",
  },
  {
    text: "The four most dangerous words in investing are: 'this time it's different.'",
    author: "John Templeton",
  },
  {
    text: "Risk comes from not knowing what you're doing.",
    author: "Warren Buffett",
  },
  {
    text: "An investment in knowledge pays the best interest.",
    author: "Benjamin Franklin",
  },
  {
    text: "The investor's chief problem — and even his worst enemy — is likely to be himself.",
    author: "Benjamin Graham",
  },
  {
    text: "In the short run the market is a voting machine; in the long run it is a weighing machine.",
    author: "Benjamin Graham",
  },
  {
    text: "Wide diversification is only required when investors do not understand what they are doing.",
    author: "Warren Buffett",
  },
  {
    text: "Successful investing takes time, discipline, and patience.",
    author: "John Bogle",
  },
  {
    text: "The market can remain irrational longer than you can remain solvent.",
    author: "John Maynard Keynes",
  },
  {
    text: "Don't look for the needle in the haystack. Just buy the haystack.",
    author: "John Bogle",
  },
  {
    text: "It's far better to buy a wonderful company at a fair price than a fair company at a wonderful price.",
    author: "Warren Buffett",
  },
  {
    text: "The best investment you can make is in yourself.",
    author: "Warren Buffett",
  },
  {
    text: "Behind every stock is a company. Find out what it's doing.",
    author: "Peter Lynch",
  },
  {
    text: "Invest for the long haul. Don't get too greedy and don't get too scared.",
    author: "Shelby M.C. Davis",
  },
  {
    text: "The most important quality for an investor is temperament, not intellect.",
    author: "Warren Buffett",
  },
  {
    text: "If you have trouble imagining a 20% loss in the stock market, you shouldn't be in stocks.",
    author: "John Bogle",
  },
];

/**
 * Pick one quote at random. Stable across the lifetime of a single loader
 * mount — call it once at component initialization, NOT in the render path.
 */
export function pickLoaderQuote() {
  const i = Math.floor(Math.random() * LOADER_QUOTES.length);
  return LOADER_QUOTES[i];
}
