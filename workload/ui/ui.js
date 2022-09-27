(function() {

  fetch('config.json')
    .then(response => response.json())
    .then(data => {

      if (data.apps && data.apps.length > 0) {
        while (data.apps.length % 3 != 0) {
          data.apps.push({})
        }
      }
      if (data.links && data.links.length > 0) {
        while (data.links.length % 3 != 0) {
          data.links.push({})
        }
      }

      const source = document.getElementById('root-template').innerHTML;
      const template = Handlebars.compile(source)
      const rendered = template(data);

      document.getElementById('root').innerHTML = rendered;
      
    })

})()