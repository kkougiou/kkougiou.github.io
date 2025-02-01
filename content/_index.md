---
# Leave the homepage title empty to use the site title
title: ''
date: 2022-10-24
type: landing

sections:
  - block: about.biography
    id: about
    content:
      title: Biography
      # Choose a user profile to display (a folder name within `content/authors/`)
      username: admin
  - block: collection
    id: featured
    content:
      title: Featured Publications
      filters:
        folders:
          - publication
        featured_only: true
    design:
      columns: '2'
      view: card
  - block: collection
    id: publications
    content:
      title: Publications
      filters:
        folders:
          - publication
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
