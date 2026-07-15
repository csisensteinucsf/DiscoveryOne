import './utils/autofillNewCase.js';
import { installCsrfFetch } from './utils/csrfFetch.js'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App.jsx'
import './styles.css';

if (typeof document !== 'undefined') {
  document.title = 'DiscoveryOne'
}
installCsrfFetch()

createRoot(document.getElementById('root')).render(
  <BrowserRouter><App /></BrowserRouter>
)
