import './globals.css';

export const metadata = { title: 'DISHA HR' };
export const viewport = { width: 'device-width', initialScale: 1, themeColor: '#2451b7' };

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
