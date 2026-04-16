import { Inter } from "next/font/google";
import "./globals.css";
import { AuthProvider } from "./context/AuthContext";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
});

export const metadata = {
  title: "FinContext — AI-Powered Market Intelligence",
  description:
    "Contextual analysis for Indian equities. Understand why stocks move with AI-synthesized market context from global macro, local news, and sector trends.",
  keywords: [
    "Indian stocks",
    "market analysis",
    "AI",
    "RAG",
    "financial intelligence",
    "mid-cap",
    "large-cap",
  ],
};

export default function RootLayout({ children }) {
  return (
    <html lang="en" className={inter.variable}>
      <body className="antialiased">
        <AuthProvider>{children}</AuthProvider>
      </body>
    </html>
  );
}
