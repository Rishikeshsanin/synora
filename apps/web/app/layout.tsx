import type { Metadata } from "next";
import "./globals.css";
export const metadata: Metadata = {title:"Synora — Make sound your own",description:"A creative workspace for original music and sound.",referrer:"no-referrer"};
export default function Layout({children}:{children:React.ReactNode}){return <html lang="en"><body>{children}</body></html>}
