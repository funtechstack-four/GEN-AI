# web

Next.js 14 front end for the Land Title Due-Diligence Agent: the intake form and the dossier page.

```
cd web
npm install
npm run dev        # http://localhost:3100
```

It runs on port **3100** because 3000 is the Zetaris UI coming through the SSH tunnel.

The form posts to `POST /dossier` on the agents API (`NEXT_PUBLIC_API_URL`, default `http://localhost:8000`). Until that API is running, the page falls back to a mock in `lib/mockDossier.ts` and shows a "Demo data" banner. The mock knows three shapes:

| Input | Verdict |
|---|---|
| Title serial 5253001–5253367 | STOP |
| Parcel containing `12715/288` | HIGH RISK (with a rejected claim about `/289`) |
| Anything else | VERIFY FIRST |

`lib/contracts.ts` mirrors the frozen contracts in `agents/contracts.py`. If those change, update this file to match.
