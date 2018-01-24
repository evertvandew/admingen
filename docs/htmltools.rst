

General principles
---------------------

The htmltools give a functional-style method for generating HTML from Python code.
There are also tools for generating forms and other components.

The tooling expects either HTML string directly or callable objects that return HTML strings
when called.

Often the functions allow keyword arguments that are added to the relevant HTML tags as arguments.


Benefits of the function-based structure
--------------------------------------------

Due to the choices made, it is very easy to create re-usable components. Much easier than
when using the normal template-based approach. Also it is very easy to completely change the
technology used to implement the HMI, e.g. using different HTML frameworks or some other
GUI technology.

Buttons and button bars
--------------------------

Example:

    button = Button('<i class="fa fa-paper-plane"></i>', btn_type=['success', 'xs'],
                    target='/versturen)()

The first element is what is rendered in the actual button. The btn_type is used to format
the button, in this case using bootstrap css classes.
The target is the action that is to be taken. In the current version, this is an URL where
button relates to using an A HREF tag.

Buttons can be combined in a button bar, for example

    btnbar = ButtonBar(*btns)

where btns is a list of Buttons.

Forms
------

The ability to auto-generate forms is one of the main goals of this framework. For this a form
component is needed. It is supplied by the SimpleForm function.

    def SimpleForm(*args, validator=None, defaults={}, success=None, action='POST',
                   submit='Opslaan', enctype="multipart/form-data", readonly=False, cancel=None):

The arguments are:

* args: a list of 'fields', functions that return a specific field tied to a specific variable.
* validator: an optional function that checks all the values that are submitted.
* defaults: a dictionary with default or initial values for the form.
* success: a function to be called when the form is successfully submitted. This function must
  process the arguments and perform the required action (such as storing them in a database).
  If success is not defined, no buttons will be generated.
* action: optional HTTP verb to use on submit. Usually the default POST is OK.
* submit: the text shown on the 'submit' button. There are no other buttons, but the form can
  be wrapped in a container with other buttons.
* cancel: URL to be called on an optional 'cancel' button.
* enctype: the encoding to use when submitting the data.
* readonly: an optional flag to indicate whether the user can edit (and submit) the data.

Due to the combinations of flags and fields, the component can generate many different forms,
such as viewers, editors, dialogs before deleting, adding or updating a value, etc.

It is used to generate the form for e.g. the CRUD component from a database table definition.

The validator function receives the list of keyword arguments corresponding to the parameters that
were submitted. It must return two dictionaries, one with the final values to be passed to the
success function, and one containing the errors for each argument that does not validate. If there
are errors, success will not be called. Instead the errors are shown with each field.

The success function receives a list of keyword arguments that passed through the validator,
and must return the HTML to be shown, or redirect to another URL.

Example: a simple login form
................................

def check(**kwargs):
    """ Check the credentials of a proposed user.
    """
    if not (kwargs[UNAME_FIELD_NAME] and kwargs[PWD_FIELD_NAME]):
        return kwargs, {UNAME_FIELD_NAME: 'Zowel naam als wachtwoord invullen!'}
    with model.sessionScope():
        user = model.User.get(name=kwargs[UNAME_FIELD_NAME])
        if user:
            if model.checkpasswd(kwargs[PWD_FIELD_NAME], user.password):
                return kwargs, {}
    return kwargs, {UNAME_FIELD_NAME: 'Fout in gebruikersnaam of wachtwoord'}

def success(**kwargs):
    """ The user was authenticated. Update the session to reflect this.
    """
    with model.sessionScope():
        user = model.User.get(name=kwargs[UNAME_FIELD_NAME])
        cherrypy.session['user_id'] = user.id
        cherrypy.session['username'] = user.name
        cherrypy.session['role'] = user.role

@cherrypy.expose
def handle_login(**kwargs):
    form = SimpleForm(String(UNAME_FIELD_NAME, 'Gebruikersnaam'),
                      EnterPassword('password', 'Wachtwoord'),
                      validator=check,
                      success=success)
    return Page(Title('Please Login'), form)



Tables
-------------

  PaginatedTable(line, data, header=None, row_select_url=None)



Form Generators
------------------


annotationsForm: Generate a form from an annotated (data) class. For example:

@dataclass
class AddressData:
    name: str
    address: str
    city: str
    telephone: str
    email: str

def success(

form = annotationsForm(AddressData


generateCrud




Mechanisms / Contracts
-------------------------

Contract for select fields

Contract for fields in a form

Mechanism for paginated tables
................................