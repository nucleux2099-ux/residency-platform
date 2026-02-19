import type { Config } from 'tailwindcss'

const config: Config = {
    content: [
        './src/pages/**/*.{js,ts,jsx,tsx,mdx}',
        './src/components/**/*.{js,ts,jsx,tsx,mdx}',
        './src/app/**/*.{js,ts,jsx,tsx,mdx}',
    ],
    theme: {
        extend: {
            fontFamily: {
                sans: ['Inter', 'sans-serif'],
            },
            colors: {
                primary: {
                    50: '#ecf4fc',
                    100: '#d8e8f7',
                    300: '#7fb1d8',
                    500: '#286ea0',
                    600: '#1d5a88',
                    700: '#17486d',
                },
                slate: {
                    25: '#fbfcfd',
                    50: '#f4f6fa',
                    100: '#e9edf4',
                    200: '#d6dde8',
                    300: '#bdc8d8',
                    500: '#62718b',
                    700: '#344159',
                    900: '#172033',
                }
            }
        },
    },
    plugins: [],
}
export default config
