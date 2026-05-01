# Solar_System_Instructor NotebookLM Sources

Use these source URLs for the first focused NotebookLM notebook. Keep the first dataset pass narrow: Solar System structure, planets, dwarf planets, small bodies, and orbital scale.

- https://science.nasa.gov/solar-system/overview/
- https://science.nasa.gov/solar-system/planets/
- https://science.nasa.gov/solar-system/asteroids
- https://science.nasa.gov/solar-system/comets
- https://science.nasa.gov/solar-system/kuiper-belt/facts
- https://science.nasa.gov/solar-system/oort-cloud/facts/

After NotebookLM auth is available:

```bash
notebooklm create "Solar_System_Instructor" --json
notebooklm source add https://science.nasa.gov/solar-system/overview/ --notebook <NOTEBOOK_ID> --type url
notebooklm source add https://science.nasa.gov/solar-system/planets/ --notebook <NOTEBOOK_ID> --type url
notebooklm source add https://science.nasa.gov/solar-system/asteroids --notebook <NOTEBOOK_ID> --type url
notebooklm source add https://science.nasa.gov/solar-system/comets --notebook <NOTEBOOK_ID> --type url
notebooklm source add https://science.nasa.gov/solar-system/kuiper-belt/facts --notebook <NOTEBOOK_ID> --type url
notebooklm source add https://science.nasa.gov/solar-system/oort-cloud/facts/ --notebook <NOTEBOOK_ID> --type url
```
