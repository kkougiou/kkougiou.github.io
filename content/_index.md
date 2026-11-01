---
# Leave the homepage title empty to use the site title
title: ''
date: 2022-10-24
type: landing

sections:
  - block: landing_hero
    id: hero
    content:
      title: Konstantinos Kougioumoutzis
      text: Plant taxonomy, biogeography and conservation of the Greek and Mediterranean flora
      image: hero-landscape.jpg
      alt: Rocky mountain valley with a conifer in the foreground
    design:
      spacing:
        padding: ['0', '0', '0', '0']
  - block: about.biography
    id: about
    content:
      title: Biography
      # Choose a user profile to display (a folder name within `content/authors/`)
      username: admin
  - block: features
    id: research
    content:
      title: Research
      text: ''
      items:
        - name: Island & mountain biogeography
          icon: mountain
          icon_pack: fas
          description: How area, isolation, geological history and past sea-level change shape plant diversity and endemism across the Aegean islands and the Greek mountains.
        - name: Global change & distributions
          icon: globe-europe
          icon_pack: fas
          description: Species distribution models and ensembles of small models for range-restricted endemics under future climate and land-use change, and how well protected areas will keep up.
        - name: Taxonomy & extinction risk
          icon: seedling
          icon_pack: fas
          description: Morphometric taxonomy, new taxa and rediscoveries, floristic inventories, IUCN Red List assessments and conservation genetics of threatened Greek plants.
    design:
      columns: '1'
  - block: collection
    id: featured
    content:
      title: Selected publications
      filters:
        folders:
          - publication
        featured_only: true
    design:
      columns: '1'
      view: card
  - block: collection
    id: publications
    content:
      title: Recent publications
      count: 6
      filters:
        folders:
          - publication
        exclude_featured: false
      sort_by: 'date'
      sort_ascending: false
    design:
      columns: '2'
      view: citation
  - block: contact
    id: contact
    content:
      title: Contact
      subtitle:
      email: kkougiou@aua.gr
      address:
        street: Laboratory of Botany, Department of Biology
        city: Patras
        region: Achaia
        postcode: '26504'
        country: Greece
        country_code: GR
      coordinates:
        latitude: '38.2894'
        longitude: '21.7868'
      autolink: true
      form:
        provider: none
    design:
      columns: '2'
---
